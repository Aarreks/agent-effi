import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from backend import main
from backend.store import Store

@pytest.fixture
def staff(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path/'access.sqlite3'))
    monkeypatch.setenv('VOICE_PROVIDER','openai');monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with TestClient(main.app) as client:
        assert client.post('/auth/login',json={'password':'test-staff-password'}).status_code==200
        yield client

def test_anonymous_reads_writes_and_websocket_are_blocked(staff):
    staff.cookies.clear()
    for method,path in [('GET','/cases'),('GET','/calls'),('POST','/calls/test'),('POST','/voice/session'),('GET','/docs')]:
        assert staff.request(method,path).status_code==401
    assert staff.get('/health').status_code==200
    assert staff.get('/auth/me').json()=={'authenticated':False}
    with pytest.raises(WebSocketDisconnect):
        with staff.websocket_connect('/events'):pass

def test_worker_only_accesses_bound_call_and_linked_case(staff):
    first=staff.post('/calls/test').json()['id'];second=staff.post('/calls/test').json()['id']
    body=dict(call_id=first,name='Jordan',phone='4155550134',issue_type='pothole',description='A large pothole.',location='Cedar')
    case=staff.post('/cases',json=body).json()
    other=staff.post('/cases',json={**body,'call_id':second}).json()
    staff.cookies.clear();staff.headers.update({'Authorization':'Bearer '+'w'*32,'X-Call-ID':first})
    assert staff.get('/calls/'+first).status_code==200
    assert staff.get('/cases/'+case['id']).status_code==200
    for path in ['/cases','/calls','/calls/'+second,'/cases/'+other['id']]:assert staff.get(path).status_code==403
    assert staff.get('/cases/lookup',params={'call_id':second,'case_id':other['id']}).status_code==403
    assert staff.post('/cases',json={**body,'call_id':second}).status_code==403
    assert staff.patch('/cases/'+case['id'],json={'call_id':first,'status':'resolved'}).status_code==403
    assert staff.patch('/cases/'+other['id'],json={'call_id':first,'action_id':'cross','note':'Bad scope'}).status_code==403
    assert staff.patch('/cases/'+case['id'],json={'call_id':first,'action_id':'valid','note':'Confirmed resident detail'}).status_code==200
    assert staff.post('/calls/'+second+'/transcript',json={'id':'bad','role':'user','text':'Wrong call'}).status_code==403
    assert staff.post('/calls/'+first+'/transcript',json={'id':'good','role':'user','text':'My information'}).status_code==200
    assert staff.post('/voice/session').status_code==403

def test_logout_cookie_flags_and_origin_checks(staff):
    response=staff.post('/auth/login',json={'password':'test-staff-password'})
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'max-age=28800' in cookie
    assert staff.post('/calls/test',headers={'Origin':'https://untrusted.example'}).status_code==403
    with pytest.raises(WebSocketDisconnect):
        with staff.websocket_connect('/events',headers={'Origin':'https://untrusted.example'}):pass
    assert staff.post('/auth/logout').status_code==200
    assert staff.get('/cases').status_code==401
    assert staff.post('/auth/login',json={'password':'wrong-password'}).status_code==401

def test_missing_access_config_fails_closed(staff,monkeypatch):
    monkeypatch.delenv('VOICE_WORKER_TOKEN')
    assert staff.get('/cases').status_code==503

def test_worker_can_collect_and_create_in_its_call(staff):
    call_id=staff.post('/calls/test').json()['id']
    staff.cookies.clear();staff.headers.update({'Authorization':'Bearer '+'w'*32,'X-Call-ID':call_id})
    assert staff.patch('/calls/'+call_id+'/intake',json={'name':'Jordan','stage':'collecting'}).status_code==200
    assert staff.patch('/calls/'+call_id+'/intake',json={'phone':'1','stage':'collecting'}).status_code==422
    assert 'phone' not in staff.get('/calls/'+call_id).json()['intake']
    response=staff.post('/cases',json=dict(call_id=call_id,name='Jordan',phone='4155550134',issue_type='pothole',description='A large pothole.',location='Cedar'))
    assert response.status_code==201
    assert staff.get('/cases/'+response.json()['id']).status_code==200


def test_fresh_intake_removes_worker_access_to_previous_case(staff):
    old_call=staff.post('/calls/test').json()['id']
    case=staff.post('/cases',json=dict(call_id=old_call,name='Alex Wen',phone='4153069766',issue_type='other',description='Skipped street cleaning',location='Claremont')).json()
    call_id=staff.post('/calls/test').json()['id']
    staff.cookies.clear();staff.headers.update({'Authorization':'Bearer '+'w'*32,'X-Call-ID':call_id})
    assert staff.get('/cases/lookup',params={'call_id':call_id,'case_id':case['id']}).status_code==200
    assert staff.patch('/calls/'+call_id+'/intake',json={'start_new':True}).status_code==200
    assert staff.get('/cases/'+case['id']).status_code==403
    assert staff.patch('/cases/'+case['id'],json={'call_id':call_id,'action_id':'old','note':'Wrong case'}).status_code==403
    assert staff.patch('/calls/'+old_call+'/intake',json={'start_new':True}).status_code==403
    assert staff.patch('/calls/'+call_id+'/intake',json={'name':'Troy Zhang','phone':'8427892014'}).json()['intake']['name']=='Troy Zhang'

def test_login_attempts_are_limited(staff):
    staff.cookies.clear()
    for _ in range(5):assert staff.post('/auth/login',json={'password':'wrong-password'}).status_code==401
    assert staff.post('/auth/login',json={'password':'test-staff-password'}).status_code==429
