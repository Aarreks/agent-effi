import asyncio
import os
import uuid
import re
import time
from contextlib import asynccontextmanager
from typing import Literal
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel, Field, field_validator
from .store import Store, now, phone_key
from .analysis import analyze
from .providers import configured, provider
from . import auth
from fastapi.responses import JSONResponse

load_dotenv('.env')
store=Store(os.getenv('DATABASE_PATH','data/effigov.sqlite3'))
listeners: set[asyncio.Queue] = set()
analysis_locks: dict[str,asyncio.Lock] = {}
captions: dict[str,dict] = {}


def notify(kind, identity=None):
    for queue in list(listeners):
        try:
            queue.put_nowait(dict(type=kind,id=identity))
        except asyncio.QueueFull:
            pass  # UI refetches a full snapshot, so coalescing is safe.


async def finish_analysis(call_id):
    async with analysis_locks.setdefault(call_id,asyncio.Lock()):
        call=store.call(call_id)
        fingerprint='|'.join(t['id'] for t in call['transcript'])
        if call.get('analysis_fingerprint') == fingerprint and call['analysis_status']=='complete':
            return
        if not configured():
            store.update_call(call_id,analysis_status='unavailable',analysis_error='Model credentials are not configured. Connect LiveKit Cloud or configure OpenAI.')
            notify('call',call_id)
            return
        store.update_call(call_id,analysis_status='analyzing')
        notify('call',call_id)
        try:
            transcript='\n'.join(f"{t['role']}: {t['text']}" for t in call['transcript'])
            if call['case_id']:
                transcript+='\nBackend confirmed case: '+str(store.case(call['case_id']))
            result=await analyze(transcript)
            store.update_call(call_id,analysis_status='complete',analysis=result,analysis_fingerprint=fingerprint,analysis_error=None)
        except Exception as exc:
            store.update_call(call_id,analysis_status='failed',analysis_error=f'Analysis failed ({type(exc).__name__}). Retry is available.')
        notify('call',call_id)


app=FastAPI(title='EffiGov Voice Desk',version='0.1.0')
def trusted_origin(origin):
    return not origin or origin in {os.getenv('FRONTEND_ORIGIN','http://127.0.0.1:3060'),'http://localhost:3060'}


@app.middleware('http')
async def access_control(request,call_next):
    path=request.url.path
    if path=='/health':return await call_next(request)
    if not auth.configured():return JSONResponse(status_code=503,content={'detail':'Staff access is not configured. Run the setup script.'})
    if path in {'/auth/login','/auth/me'}:
        if request.method!='GET' and not trusted_origin(request.headers.get('origin')):
            return JSONResponse(status_code=403,content={'detail':'Untrusted origin'})
        return await call_next(request)
    if auth.verify_staff(request.cookies.get(auth.COOKIE_NAME)):
        if request.method not in {'GET','HEAD','OPTIONS'} and not trusted_origin(request.headers.get('origin')):
            return JSONResponse(status_code=403,content={'detail':'Untrusted origin'})
        return await call_next(request)
    if not auth.verify_worker(request.headers.get('authorization')):
        return JSONResponse(status_code=401,content={'detail':'Staff sign-in required'})
    call_id=auth.worker_call_id(request.headers.get('x-call-id'))
    allowed=False
    if call_id:
        try:
            call=store.call(call_id)
            method=request.method
            if path==f'/calls/{call_id}':allowed=method=='GET'
            if re.fullmatch(r'/calls/'+re.escape(call_id)+r'/(active|transcript|caption|supervisor|finish|fail)',path):allowed=method=='POST'
            if path==f'/calls/{call_id}/intake':allowed=method=='PATCH'
            if path=='/cases/lookup':allowed=method=='GET' and request.query_params.get('call_id')==call_id
            if path=='/cases' and method=='POST':allowed=(await request.json()).get('call_id')==call_id
            if re.fullmatch(r'/cases/EG-[A-F0-9]{6}',path):
                if method=='GET':allowed=call['case_id']==path.rsplit('/',1)[1]
                elif method=='PATCH':
                    body=await request.json()
                    allowed=body.get('call_id')==call_id and set(body)<={'call_id','action_id','note'} and call['case_id']==path.rsplit('/',1)[1]
        except (KeyError,ValueError,TypeError):pass
    if not allowed:return JSONResponse(status_code=403,content={'detail':'Voice worker access is limited to its call and linked case'})
    return await call_next(request)


login_failures={}

class StaffLogin(BaseModel):
    password: str=Field(max_length=1024)


@app.get('/auth/me')
async def who_am_i(request: Request):
    return {'authenticated':auth.verify_staff(request.cookies.get(auth.COOKIE_NAME))}


@app.post('/auth/login')
async def login(body: StaffLogin,request: Request):
    host=request.client.host if request.client else 'unknown'
    attempts=[t for t in login_failures.get(host,[]) if time.monotonic()-t<300]
    login_failures[host]=attempts
    if len(attempts)>=5:raise HTTPException(429,'Too many attempts. Try again in five minutes.')
    token=auth.sign_in(body.password)
    if token is None:
        attempts.append(time.monotonic())
        raise HTTPException(401,'Incorrect staff password')
    login_failures.pop(host,None)
    response=JSONResponse({'authenticated':True})
    response.set_cookie(auth.COOKIE_NAME,token,**auth.session_cookie_options())
    return response


@app.post('/auth/logout')
async def logout():
    response=JSONResponse({'authenticated':False})
    response.delete_cookie(auth.COOKIE_NAME,path='/')
    return response


@app.exception_handler(KeyError)
async def missing(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404,content={'detail':'Record not found'})


@app.exception_handler(ValueError)
async def conflict(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409,content={'detail':str(exc)})


class CaseCreate(BaseModel):
    call_id: str
    name: str = Field(min_length=1,max_length=100)
    phone: str = Field(min_length=7,max_length=30)
    issue_type: Literal['missed_collection','pothole','streetlight','other']
    description: str = Field(min_length=5,max_length=4000)
    location: str = Field(default='',max_length=300)

    @field_validator('name','description')
    @classmethod
    def not_blank(cls,value):
        if not value.strip(): raise ValueError('Cannot be blank')
        return value.strip()

    @field_validator('phone')
    @classmethod
    def valid_phone(cls,value):
        if len(''.join(c for c in value if c.isdigit())) < 7: raise ValueError('Use at least seven phone digits')
        return value


class CasePatch(BaseModel):
    revision: int | None = None
    status: Literal['new','in_progress','resolved'] | None = None
    note: str | None = Field(default=None,min_length=1,max_length=4000)
    location: str | None = Field(default=None,max_length=300)
    description: str | None = Field(default=None,min_length=5,max_length=4000)
    call_id: str | None = None
    action_id: str | None = None


class Turn(BaseModel):
    id: str
    role: Literal['user','assistant']
    text: str = Field(min_length=1,max_length=20000)


class Caption(BaseModel):
    role: Literal['user','assistant']
    text: str = Field(max_length=20000)


class CallFailure(BaseModel):
    reason: str = Field(min_length=1,max_length=300)


class IntakePatch(BaseModel):
    name: str | None = Field(default=None,min_length=1,max_length=100)
    phone: str | None = Field(default=None,min_length=1,max_length=30)
    issue_type: Literal['missed_collection','pothole','streetlight','other'] | None = None
    description: str | None = Field(default=None,min_length=1,max_length=4000)
    location: str | None = Field(default=None,min_length=1,max_length=300)
    stage: Literal['collecting','awaiting_confirmation'] = 'collecting'


class SupervisorReview(BaseModel):
    event_id: str = Field(min_length=1,max_length=200)
    status: Literal['checked','corrected','failed']
    utterance: str = Field(min_length=1,max_length=20000)
    reason: str = Field(default='',max_length=4000)
    correction: str = Field(default='',max_length=4000)


@app.get('/health')
async def health():
    return dict(ok=True,voice_configured=configured(),voice_provider=provider(),livekit_url=os.getenv('LIVEKIT_URL','ws://127.0.0.1:7880'))


@app.get('/cases')
async def cases(search: str='',status: str=''):
    return [c for c in store.listing('cases') if (not status or c['status']==status) and (not search or search.lower() in ' '.join(str(c[k]) for k in ['id','name','phone','description','location']).lower())]


@app.get('/cases/lookup')
async def lookup(call_id: str,case_id: str='',phone: str=''):
    store.call(call_id)
    if not case_id and not phone: raise HTTPException(422,'Provide a case ID or phone number')
    # Spoken identifiers may arrive with spaces or without their display hyphen.
    key=''.join(case_id.split()).replace('-','').upper()
    matches=[c for c in store.listing('cases') if
             (c['id'].replace('-','').upper()==key if case_id else phone_key(c['phone'])==phone_key(phone))]
    if len(matches)==1:
        store.attach(call_id,matches[0]['id'])
        notify('call',call_id)
    return matches[:5]


@app.get('/cases/{case_id}')
async def case(case_id: str):
    return store.case(case_id)


@app.post('/cases',status_code=201)
async def create(body: CaseCreate):
    fields=body.model_dump(exclude={'call_id'})
    result=store.create_case(body.call_id,fields)
    notify('case',result['id'])
    return result


@app.patch('/cases/{case_id}')
async def patch(case_id: str,body: CasePatch):
    if body.call_id and body.status is not None:
        raise HTTPException(422,'Residents may add details; only staff change service status')
    fields=body.model_dump(exclude_none=True,exclude={'revision','call_id','action_id'})
    if not fields: raise HTTPException(422,'No changes supplied')
    result=store.patch_case(case_id,fields,actor='voice' if body.call_id else 'staff',call_id=body.call_id,action_id=body.action_id,revision=body.revision)
    notify('case',case_id)
    return result


@app.get('/calls')
async def calls():
    return store.listing('calls')


@app.get('/calls/{call_id}')
async def call(call_id: str):
    return {**store.call(call_id),'live_caption':captions.get(call_id)}


@app.post('/calls/test',status_code=201)
async def test_call():
    result=store.start_call('test')
    notify('call',result['id'])
    return result


@app.post('/calls/{call_id}/active')
async def active(call_id: str):
    call=store.call(call_id)
    if call['status'] not in {'ended','failed'}:
        call=store.update_call(call_id,status='active')
        notify('call',call_id)
    return call


@app.post('/calls/{call_id}/transcript')
async def transcript(call_id: str,body: Turn):
    result=store.turn(call_id,body.id,body.role,body.text)
    caption=captions.get(call_id,{})
    if caption.get('role')==body.role and caption.get('at','')<=result['at']:captions.pop(call_id,None)
    notify('transcript',call_id)
    return result


@app.post('/calls/{call_id}/caption')
async def live_caption(call_id: str,body: Caption):
    call=store.call(call_id)
    if call['status'] in {'ended','failed'}:raise HTTPException(409,'Call has ended')
    if body.text:captions[call_id]={**body.model_dump(),'at':now()}
    else:captions.pop(call_id,None)
    notify('caption',call_id)
    return {'accepted':True}


@app.patch('/calls/{call_id}/intake')
async def intake(call_id: str,body: IntakePatch):
    fields=body.model_dump(exclude_none=True,exclude={'stage'})
    if not fields:raise HTTPException(422,'Supply at least one collected detail')
    result=store.update_intake(call_id,fields,body.stage)
    notify('call',call_id)
    return result


@app.post('/calls/{call_id}/supervisor')
async def supervisor(call_id: str,body: SupervisorReview):
    result=store.supervisor_review(call_id,body.event_id,body.model_dump(exclude={'event_id'}))
    notify('call',call_id)
    return result


@app.post('/calls/{call_id}/finish')
async def finish(call_id: str,tasks: BackgroundTasks):
    existing=store.call(call_id)
    call=store.update_call(call_id,status='failed' if existing['status']=='failed' else 'ended',ended_at=existing['ended_at'] or now())
    captions.pop(call_id,None)
    notify('call',call_id)
    tasks.add_task(finish_analysis,call_id)
    return call


@app.post('/calls/{call_id}/fail')
async def fail_call(call_id: str,body: CallFailure):
    call=store.update_call(call_id,status='failed',ended_at=now(),error=body.reason)
    captions.pop(call_id,None)
    notify('call',call_id)
    return call


@app.post('/calls/{call_id}/analyze')
async def retry_analysis(call_id: str,tasks: BackgroundTasks):
    call=store.call(call_id)
    if call['status'] != 'ended': raise HTTPException(409,'End the call before analysis')
    tasks.add_task(finish_analysis,call_id)
    return {'queued':True}


@app.post('/voice/session',status_code=201)
async def voice_session():
    if not configured():
        raise HTTPException(503,'Connect LiveKit Cloud or set OPENAI_API_KEY in submission/.env and restart to enable AI voice.')
    call=store.start_call()
    notify('call',call['id'])
    room='effigov-'+call['id']
    url=os.getenv('LIVEKIT_URL','ws://127.0.0.1:7880')
    key=os.getenv('LIVEKIT_API_KEY','devkey'); secret=os.getenv('LIVEKIT_API_SECRET','secret')
    try:
        async with api.LiveKitAPI(url=url,api_key=key,api_secret=secret) as lk:
            await lk.room.create_room(api.CreateRoomRequest(name=room,empty_timeout=60))
            import json
            await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(agent_name='effigov',room=room,metadata=json.dumps({'call_id':call['id']})))
    except Exception as exc:
        store.update_call(call['id'],status='failed',ended_at=now(),error='Unable to reach LiveKit server')
        notify('call',call['id'])
        raise HTTPException(503,'Cannot connect to LiveKit. Start the server and voice worker.') from exc
    token=(api.AccessToken(key,secret).with_identity('resident-'+uuid.uuid4().hex).with_name('Resident').with_grants(api.VideoGrants(room_join=True,room=room)).with_ttl(__import__('datetime').timedelta(minutes=30)).to_jwt())
    return dict(call_id=call['id'],url=url,token=token)


@app.websocket('/events')
async def events(socket: WebSocket):
    if not auth.configured() or not auth.verify_staff(socket.cookies.get(auth.COOKIE_NAME)) or not trusted_origin(socket.headers.get('origin')):
        await socket.close(code=1008)
        return
    await socket.accept()
    queue=asyncio.Queue(maxsize=100)
    listeners.add(queue)
    try:
        await socket.send_json({'type':'connected'})
        while True:
            try:
                await socket.send_json(await asyncio.wait_for(queue.get(),timeout=15))
            except asyncio.TimeoutError:
                await socket.send_json({'type':'heartbeat'})
    except (WebSocketDisconnect,RuntimeError):
        pass
    finally:
        listeners.discard(queue)
