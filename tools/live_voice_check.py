"""Paid live voice smoke check, using Windows speech synthesis instead of a microphone.

Run only with configured model credentials and a running API/voice worker.
Creates fictional cases in the local demo database. No simulated agent replies.
"""
import asyncio
import gc
import json
import subprocess
import sys
import os
import time
from pathlib import Path
import av
import httpx
from livekit import rtc
from websockets.asyncio.client import connect
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.stderr.reconfigure(encoding='utf-8',errors='replace')


def synthesize(text,name):
    output=ROOT/'data'/'voice-check'/f'{name}.wav'
    output.parent.mkdir(parents=True,exist_ok=True)
    text=text.replace("'","''")
    path=str(output).replace("'","''")
    script=f"Add-Type -AssemblyName System.Speech; $speech=New-Object System.Speech.Synthesis.SpeechSynthesizer; $speech.SetOutputToWaveFile('{path}'); $speech.Speak('{text}'); $speech.Dispose()"
    subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-Command',script],check=True,capture_output=True)
    return output


async def main():
    policy_check=any(flag in sys.argv for flag in ['--policy-check','--smoke-check','--input-check','--location-check'])
    public_check='--public' in sys.argv
    lookup=next((arg for arg in sys.argv[1:] if not arg.startswith('--')),None)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8060',timeout=30) as client:
        login=await client.post('/auth/login',json={'password':os.environ['STAFF_PASSWORD']});login.raise_for_status()
        requested_at=time.perf_counter()
        if public_check:
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8060',timeout=30) as visitor:
                session_response=await visitor.post('/public/voice/session')
        else:
            session_response=await client.post('/voice/session')
        session_response.raise_for_status()
        info=session_response.json();call_id=info['call_id']
        print('Live voice call',call_id,flush=True)
        room=rtc.Room();source=rtc.AudioSource(24000,1);audio_frames=0
        first_audio_at=None
        read_tasks=[]
        caption_events=0

        async def watch_events():
            nonlocal caption_events
            cookie='; '.join(f'{k}={v}' for k,v in client.cookies.items())
            async with connect('ws://127.0.0.1:8060/events',additional_headers={'Cookie':cookie}) as socket:
                async for message in socket:
                    event=json.loads(message)
                    if event.get('id')==call_id and event['type']=='caption':caption_events+=1

        event_task=asyncio.create_task(watch_events())

        @room.on('track_subscribed')
        def track(track,publication,participant):
            if track.kind!=rtc.TrackKind.KIND_AUDIO:return
            async def read():
                nonlocal audio_frames,first_audio_at
                stream=rtc.AudioStream(track)
                try:
                    async for event in stream:
                        audio_frames+=1
                        if first_audio_at is None and any(event.frame.data):first_audio_at=time.perf_counter()
                finally:await stream.aclose()
            read_tasks.append(asyncio.create_task(read()))

        async def speak(text,name):
            print('Resident audio:',text,flush=True)
            path=await asyncio.to_thread(synthesize,text,name)
            resampler=av.AudioResampler(format='s16',layout='mono',rate=24000)
            with av.open(str(path)) as container:
                for frame in container.decode(audio=0):
                    for converted in resampler.resample(frame):
                        data=converted.to_ndarray().tobytes()
                        await source.capture_frame(rtc.AudioFrame(data=data,sample_rate=24000,num_channels=1,samples_per_channel=converted.samples))
                for converted in resampler.resample(None):
                    await source.capture_frame(rtc.AudioFrame(data=converted.to_ndarray().tobytes(),sample_rate=24000,num_channels=1,samples_per_channel=converted.samples))
            # Flux receives trailing silence so it can commit the spoken turn.
            for _ in range(70):
                await source.capture_frame(rtc.AudioFrame(data=b'\0'*960,sample_rate=24000,num_channels=1,samples_per_channel=480))
            await source.wait_for_playout()

        last_count=0
        async def reply(timeout=45):
            nonlocal last_count
            deadline=asyncio.get_running_loop().time()+timeout
            while asyncio.get_running_loop().time()<deadline:
                response=await client.get('/calls/'+call_id)
                response.raise_for_status();call=response.json()
                if call['status']=='failed':raise RuntimeError(call.get('error','Voice failed'))
                turns=call.get('transcript',[])
                assistants=[t for t in turns if t['role']=='assistant']
                if len(assistants)>last_count:
                    last_count=len(assistants)
                    print('Real agent:',assistants[-1]['text'],flush=True)
                    return call
                await asyncio.sleep(0.5)
            raise TimeoutError('No persisted agent reply within the time limit')

        try:
            await room.connect(info['url'],info['token'])
            track=rtc.LocalAudioTrack.create_audio_track('resident-voice-check',source)
            await room.local_participant.publish_track(track,rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
            await reply()
            if first_audio_at is not None:print(f'FIRST_AUDIO {first_audio_at-requested_at:.2f}s from session request',flush=True)
            if policy_check:
                checks=[
                    ('Am I signed in as staff or as a resident?', 'role'),
                    ('Will residents be unable to see the notes I add? Are they private?', 'privacy'),
                    ('Can you find cases just from the name Jordan Lee? I have no phone number or case number.', 'name'),
                    ('My car flipped over.', 'emergency'),
                    ('Can you help me dial nine one one?', 'dial'),
                    ('I am safe; that was just a test. Can you explain the staff and resident roles again?', 'role'),
                ]
                if '--smoke-check' in sys.argv:
                    checks=[('I smell terrible smoke what is that about?', 'emergency'),
                            ('Wait, that address is wrong. Please add a correction note.', 'paused'),
                            ('I thought you left a note about that or something.', 'paused'),
                            ('I am safe; that was just a test. Can you explain the staff and resident roles again?', 'role')]
                if '--input-check' in sys.argv:
                    checks=[('New.', 'new'),('iuhgiuqwn ciqwnguio oqrg','nonsense'),
                            ('My name is Morgan Reed.', 'phone'),('1','incomplete')]
                if '--location-check' in sys.argv:
                    checks=[('Please look up case EG-119B5C and tell me the reported location.','location'),
                            ('How long ago was it created?','age'),
                            ('I thought you left a note about correcting the address.','existing-note')]
                for text,label in checks:
                    if '--input-check' in sys.argv or '--location-check' in sys.argv:
                        print('Resident text:',text,flush=True)
                        await room.local_participant.send_text(text,topic='lk.chat')
                    else:await speak(text,'policy-'+label)
                    call=await reply()
                    spoken=[t for t in call['transcript'] if t['role']=='assistant'][-1]['text'].lower()
                    if label=='role':assert 'staff' in spoken and 'resident' in spoken,spoken
                    elif label=='privacy':assert 'staff' in spoken and ('voice' in spoken or 'lookup' in spoken),spoken
                    elif label=='name':assert 'phone' in spoken and ('case' in spoken or 'id' in spoken),spoken
                    elif label=='new':assert 'name' in spoken,spoken
                    elif label=='nonsense':assert any(word in spoken for word in ['repeat','spell','understand','clarify','clear','catch']),spoken
                    elif label=='phone':assert 'phone' in spoken,spoken
                    elif label=='incomplete':assert any(word in spoken for word in ['incomplete','too short','seven digits']) and ('number' in spoken or 'phone' in spoken),spoken
                    elif label in {'location','existing-note'}:
                        assert '430' in spoken and any(word in spoken for word in ['note','correction','corrected']),spoken
                        if label=='location' and '428' in spoken:assert spoken.index('430')<spoken.index('428'),spoken
                    elif label=='age':assert 'ago' in spoken and ('minute' in spoken or 'hour' in spoken),spoken
                    else:
                        assert '911' in spoken and ('cannot' in spoken or "can't" in spoken),spoken
                        assert '?' not in spoken and 'municipal' not in spoken and 'service request' not in spoken,spoken
                if '--location-check' in sys.argv:assert call.get('case_id')=='EG-119B5C'
                else:assert not call.get('case_id'),'Policy-only conversation unexpectedly created/linked a case'
                assert audio_frames>0
                user_text=' '.join(t['text'].lower() for t in call['transcript'] if t['role']=='user')
                if '--smoke-check' in sys.argv:assert 'smoke' in user_text and not call.get('intake')
                elif '--input-check' in sys.argv:
                    assert call.get('intake',{}).get('name')=='Morgan Reed' and not call.get('intake',{}).get('phone')
                    assert 'iuhgiuqwn' not in json.dumps(call.get('intake',{}))
                elif '--location-check' not in sys.argv:assert 'flipped' in user_text and ('nine one one' in user_text or '911' in user_text)
                print('PASS: real model policy check; input/output persisted; no case action.',flush=True)
            else:
                if lookup:
                    alphabet={'A':'Alpha','B':'Bravo','C':'Charlie','D':'Delta','E':'Echo','F':'Foxtrot','G':'Golf'}
                    spoken=', '.join(f'{c} as in {alphabet[c]}' if c in alphabet else ('dash' if c=='-' else c) for c in lookup)
                    text=f'I want an update for an existing case. The case number is {spoken}. Please look it up.'
                else:
                    text='I want to report missed trash collection. My name is Jordan Lee. My phone number is four one five, five five five, zero one three four. The location is twenty four Cedar Avenue. My trash was not collected this morning and the bin is still at the curb.'
                await speak(text,'initial')
                for index in range(5):
                    call=await reply()
                    if call.get('case_id'):break
                    assistants=[t for t in call.get('transcript',[]) if t['role']=='assistant']
                    latest=assistants[-1]['text'].lower() if assistants else ''
                    confirmation='Yes, those details are correct. Please record my request.'
                    if not lookup and 'cedar' not in latest:
                        confirmation='The street name is Cedar, spelled C E D A R. The address is twenty four Cedar Avenue. The other details are correct. Please record my request with that address.'
                    await speak(text if lookup else confirmation,'confirm-'+str(index))
                if not call.get('case_id'):raise AssertionError('Agent did not create or find a case')
                case_response=await client.get('/cases/'+call['case_id']);case_response.raise_for_status();case=case_response.json()
                assert case['name']=='Jordan Lee' and case['issue_type']=='missed_collection',case
                if not lookup:assert 'cedar' in case['location'].lower(),case
                assert audio_frames>0,'No real agent audio was received'
                if lookup and '--status-cycle' in sys.argv:
                    for status in ('resolved','in_progress'):
                        response=await client.patch('/cases/'+case['id'],json={'revision':case['revision'],'status':status})
                        response.raise_for_status();case=response.json()
                        await speak('Please look up my case again and read the latest status.','status-'+status)
                        call=await reply()
                        spoken=[t for t in call['transcript'] if t['role']=='assistant'][-1]['text'].lower()
                        assert status.replace('_',' ') in spoken,spoken
                    print('PASS: staff changed service status twice during the active call; voice read each saved status.',flush=True)
                if lookup:
                    assert case['id']==lookup,case
                    before=len(case['notes'])
                    await speak('Please add a note that the bin is still at the curb and the problem is continuing. We still see the trash outside the mailbox.','followup')
                    await reply()
                    case=(await client.get('/cases/'+call['case_id'])).json()
                    assert len(case['notes'])==before+1 and case['notes'][-1]['actor']=='voice' and 'curb' in case['notes'][-1]['text'].lower(),case
                print('PASS: live spoken audio → recognized transcript → real model/tool → persisted case; agent audio received.',flush=True)
                print('CASE',case['id'],flush=True)
            if public_check:
                async with httpx.AsyncClient(base_url='http://127.0.0.1:8060',timeout=30) as visitor:
                    headers={'Authorization':'Bearer '+info['access_token']}
                    result=await visitor.get('/public/calls/'+call_id,headers=headers)
                    result.raise_for_status();own=result.json()
                    assert own['transcript']
                    if call['case_id']:assert own['receipt']['id']==call['case_id']
                    else:assert own['receipt'] is None
                    assert all('case_snapshot' not in turn for turn in own['transcript'])
                    assert (await visitor.get('/cases',headers=headers)).status_code==401
                    assert (await visitor.get('/calls',headers=headers)).status_code==401
                    assert (await visitor.post('/public/calls/'+call_id+'/finish',headers=headers)).status_code==200
                print('PASS: anonymous public entry created a real voice call; own transcript/receipt readable; staff APIs blocked.',flush=True)
        finally:
            event_task.cancel();await asyncio.gather(event_task,return_exceptions=True)
            for task in read_tasks:task.cancel()
            await asyncio.gather(*read_tasks,return_exceptions=True)
            await source.aclose();await room.disconnect()
            await client.post('/calls/'+call_id+'/finish')
        # Analysis may finish asynchronously after the agent flushes the final transcript.
        for _ in range(40):
            call=(await client.get('/calls/'+call_id)).json()
            if call['analysis_status'] in {'complete','failed','unavailable'}:break
            await asyncio.sleep(0.5)
        print('ANALYSIS',json.dumps(call.get('analysis')),flush=True)
        assert call['analysis_status']=='complete',call.get('analysis_error')
        for _ in range(30):
            call=(await client.get('/calls/'+call_id)).json()
            assistant_ids={t['id'] for t in call.get('transcript',[]) if t['role']=='assistant'}
            reviewed_ids={r['event_id'] for r in call.get('supervisor_reviews',[])}
            if assistant_ids and assistant_ids<=reviewed_ids:break
            await asyncio.sleep(0.5)
        assert call.get('supervisor_reviews'),'No live supervisor checks completed'
        assert not any(r['status']=='failed' for r in call['supervisor_reviews']),call['supervisor_reviews']
        if '--input-check' not in sys.argv and '--location-check' not in sys.argv:
            assert caption_events>0,'No live caption WebSocket updates received'
        if not lookup and not policy_check:
            assert call.get('intake_history') and call['intake_stage']=='recorded','Live intake preview was not updated'
        print('SUPERVISOR',len(call['supervisor_reviews']),'real AI reviews persisted',flush=True)
        print('CAPTIONS',caption_events,'live WebSocket updates received',flush=True)


async def run():
    try:await main()
    finally:gc.collect()

if __name__=='__main__':asyncio.run(run())
