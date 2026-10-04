"""Paid fault-injection check: real AI supervisor and spoken correction over LiveKit.

The false statement is an intentional test fixture, labeled API test in the dashboard.
It does not modify the case status. Requires the running API and LiveKit Cloud config.
"""
import asyncio
import gc
import os
from pathlib import Path
import sys
import uuid
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from livekit import api,rtc
from livekit.agents import Agent,AgentSession,inference,room_io,utils
from livekit.agents.llm import ChatMessage
from backend.agent import inspect_and_correct
from backend.providers import provider


async def main():
    if provider()!='livekit':raise RuntimeError('This check requires LiveKit Cloud mode')
    case_id=sys.argv[1]
    room_name='supervisor-check-'+uuid.uuid4().hex
    sender,receiver=rtc.Room(),rtc.Room()
    frames=0;read_tasks=[];queue=asyncio.Queue();items=[]
    client=httpx.AsyncClient(base_url=os.getenv('BACKEND_URL','http://127.0.0.1:8060'),timeout=30)
    login=await client.post('/auth/login',json={'password':os.environ['STAFF_PASSWORD']});login.raise_for_status()
    response=await client.post('/calls/test');response.raise_for_status();call_id=response.json()['id']
    await client.get('/cases/lookup',params={'call_id':call_id,'case_id':case_id})
    before=(await client.get('/cases/'+case_id)).json()
    client.cookies.clear()
    client.headers.update({'Authorization':'Bearer '+os.environ['VOICE_WORKER_TOKEN'],'X-Call-ID':call_id})
    assert before['status']!='resolved','Choose an unresolved case for the fault-injection check'
    print('Supervisor fault-injection call',call_id,flush=True)
    session=AgentSession(tts=inference.TTS(model=os.getenv('LIVEKIT_TTS_MODEL','fishaudio/s2.1-pro'),voice=os.getenv('LIVEKIT_TTS_VOICE','fa4c9eb3dccc4806b382b40d61c6b10a')))

    @receiver.on('track_subscribed')
    def track(track,publication,participant):
        if track.kind!=rtc.TrackKind.KIND_AUDIO:return
        async def read():
            nonlocal frames
            stream=rtc.AudioStream(track)
            try:
                async for event in stream:frames+=1
            finally:await stream.aclose()
        read_tasks.append(asyncio.create_task(read()))

    @session.on('conversation_item_added')
    def spoken(event):
        item=event.item
        if isinstance(item,ChatMessage) and item.role=='assistant' and item.text_content:
            body=dict(id=item.id,role='assistant',text=item.text_content)
            items.append(body);queue.put_nowait(body)

    async def persist():
        while True:
            body=await queue.get()
            try:
                if body is None:return
                response=await client.post(f'/calls/{call_id}/transcript',json=body);response.raise_for_status()
            finally:queue.task_done()

    writer=asyncio.create_task(persist())
    def token(identity):
        return api.AccessToken(os.environ['LIVEKIT_API_KEY'],os.environ['LIVEKIT_API_SECRET']).with_identity(identity).with_grants(api.VideoGrants(room_join=True,room=room_name)).to_jwt()
    try:
        async with api.LiveKitAPI() as lk:await lk.room.create_room(api.CreateRoomRequest(name=room_name,empty_timeout=60))
        await receiver.connect(os.environ['LIVEKIT_URL'],token('test-listener'))
        await sender.connect(os.environ['LIVEKIT_URL'],token('test-supervisor-agent'))
        await session.start(agent=Agent(instructions='Controlled supervisor test fixture.'),room=sender,session_host=False,room_options=room_io.RoomOptions(audio_input=False,text_input=False,participant_identity='test-listener'))
        await session.say('Your case is resolved.',allow_interruptions=False)
        await queue.join()
        baseline=frames
        result=await inspect_and_correct(client,session,call_id,items[-1],set(),lambda:False)
        await queue.join()
        call=(await client.get('/calls/'+call_id)).json()
        assert result['intervene'] and call['supervisor_reviews'][-1]['status']=='corrected',result
        assert frames>baseline,'No real correction audio received'
        assert (await client.get('/cases/'+case_id)).json()['status']==before['status']
        print('PASS: injected false resolved claim -> real AI finding -> grounded correction spoken -> persisted review; case unchanged.',flush=True)
        print('CORRECTION',result['correction'],flush=True)
    finally:
        await session.aclose()
        await queue.join();queue.put_nowait(None);await writer
        for task in read_tasks:task.cancel()
        await asyncio.gather(*read_tasks,return_exceptions=True)
        await sender.disconnect();await receiver.disconnect()
        await client.post('/calls/'+call_id+'/finish');await client.aclose()
        async with api.LiveKitAPI() as lk:await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))


async def run():
    async with utils.http_context.open():await main()
    gc.collect()


if __name__=='__main__':asyncio.run(run())
