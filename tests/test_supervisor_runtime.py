"""Exercise live-review timing against the real local API without external models."""
import httpx
import pytest
import pytest_asyncio
from backend import agent,main
from backend.store import Store


@pytest_asyncio.fixture
async def context(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path/'runtime.sqlite3'))
    monkeypatch.setenv('VOICE_PROVIDER','openai');monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
        assert (await client.post('/auth/login',json={'password':'test-staff-password'})).status_code==200
        call=(await client.post('/calls/test')).json()
        case=(await client.post('/cases',json=dict(call_id=call['id'],name='Jordan Lee',phone='4155550134',issue_type='missed_collection',description='Trash was missed.',location='24 Cedar Avenue'))).json()
        yield client,call['id'],case


class Speaker:
    def __init__(self):self.spoken=[]
    async def say(self,text,**options):self.spoken.append(text)


@pytest.mark.asyncio
async def test_each_user_turn_gets_current_case_status(context):
    from livekit.agents.llm import ChatContext,ChatMessage
    client,call_id,case=context
    assistant=agent.ServiceAgent(call_id,client)
    for status in ['resolved','in_progress']:
        current=(await client.get('/cases/'+case['id'])).json()
        await client.patch('/cases/'+case['id'],json={'revision':current['revision'],'status':status})
        chat=ChatContext()
        await assistant.on_user_turn_completed(chat,ChatMessage(role='user',content=['What is its status?']))
        assert f'currently has status {status}' in chat.items[-1].text_content


@pytest.mark.asyncio
async def test_call_ending_during_ai_review_prevents_late_speech(context,monkeypatch):
    client,call_id,case=context;speaker=Speaker()
    item={'id':'reply-1','text':'Your case is resolved.'}
    await client.post('/calls/'+call_id+'/transcript',json={**item,'role':'assistant'})
    async def review(*args,**kwargs):
        await client.post('/calls/'+call_id+'/finish')
        return {'intervene':True,'reason':'The case is still new.','correction':'It is awaiting staff review.'}
    monkeypatch.setattr(agent,'review_reply',review)
    await agent.inspect_and_correct(client,speaker,call_id,item,set(),lambda:False)
    call=(await client.get('/calls/'+call_id)).json()
    assert speaker.spoken==[]
    assert call['supervisor_reviews'][0]['status']=='failed'
    assert 'ended before' in call['supervisor_reviews'][0]['reason']


@pytest.mark.asyncio
async def test_duplicate_reply_does_not_repeat_ai_review_or_spoken_correction(context,monkeypatch):
    client,call_id,case=context;speaker=Speaker();reviews=[]
    item={'id':'reply-1','text':'Your case is resolved.'}
    await client.post('/calls/'+call_id+'/transcript',json={**item,'role':'assistant'})
    async def review(*args,**kwargs):
        reviews.append(args)
        return {'intervene':True,'reason':'The case is still new.','correction':'It is awaiting staff review.'}
    monkeypatch.setattr(agent,'review_reply',review)
    for _ in range(2):await agent.inspect_and_correct(client,speaker,call_id,item,set(),lambda:False)
    call=(await client.get('/calls/'+call_id)).json()
    assert len(reviews)==1 and len(speaker.spoken)==1 and len(call['supervisor_reviews'])==1
    assert (await client.get('/cases/'+case['id'])).json()['status']=='new'


@pytest.mark.asyncio
async def test_emergency_prevents_a_queued_case_correction_from_interrupting(context,monkeypatch):
    client,call_id,case=context;speaker=Speaker()
    item={'id':'earlier-reply','text':'Your case is resolved.'}
    await client.post('/calls/'+call_id+'/transcript',json={**item,'role':'assistant'})
    async def review(*args,**kwargs):return {'intervene':True,'reason':'Wrong status.','correction':'The case is new.'}
    monkeypatch.setattr(agent,'review_reply',review)
    await agent.inspect_and_correct(client,speaker,call_id,item,set(),lambda:False,lambda:True)
    assert speaker.spoken==[]
    finding=(await client.get('/calls/'+call_id)).json()['supervisor_reviews'][0]
    assert finding['status']=='failed' and 'Emergency guidance took priority' in finding['reason']


@pytest.mark.asyncio
async def test_interrupted_supervisor_speech_is_not_marked_delivered(context,monkeypatch):
    client,call_id,case=context
    class InterruptedSpeech:
        interrupted=True
        def __await__(self):
            async def done():pass
            return done().__await__()
    class InterruptedSpeaker:
        def say(self,text,**options):
            assert options['allow_interruptions'] is True
            return InterruptedSpeech()
    item={'id':'reply-interrupted','text':'Your case is resolved.'}
    await client.post('/calls/'+call_id+'/transcript',json={**item,'role':'assistant'})
    async def review(*args,**kwargs):return {'intervene':True,'reason':'Wrong status.','correction':'The case is new.'}
    monkeypatch.setattr(agent,'review_reply',review)
    await agent.inspect_and_correct(client,InterruptedSpeaker(),call_id,item,set(),lambda:False)
    finding=(await client.get('/calls/'+call_id)).json()['supervisor_reviews'][0]
    assert finding['status']=='failed' and 'interrupted' in finding['reason']


@pytest.mark.asyncio
async def test_review_uses_recorded_facts_after_staff_status_change(context,monkeypatch):
    client,call_id,case=context;speaker=Speaker()
    item={'id':'reply-1','text':'Your request is awaiting staff review.'}
    await client.post('/calls/'+call_id+'/transcript',json={**item,'role':'assistant'})
    await client.patch('/cases/'+case['id'],json={'revision':1,'status':'resolved'})
    async def review(text,transcript,snapshot,**kwargs):
        assert snapshot['status']=='new'
        return {'intervene':False,'reason':'','correction':''}
    monkeypatch.setattr(agent,'review_reply',review)
    await agent.inspect_and_correct(client,speaker,call_id,item,set(),lambda:False)
    assert speaker.spoken==[]
    assert (await client.get('/calls/'+call_id)).json()['supervisor_reviews'][0]['status']=='checked'


@pytest.mark.asyncio
async def test_backend_receipt_blocks_false_unsaved_verdict_for_repeated_note(context,monkeypatch):
    from types import SimpleNamespace
    from backend import supervision
    client,call_id,case=context;speaker=Speaker()
    assistant=agent.ServiceAgent(call_id,client)
    note='Resident-reported address correction: between 17th and 18th (previously Seventeenth and Sepulveda)'
    for action_id in ['first-note','requested-repeat']:
        result=await assistant.add_case_note(SimpleNamespace(function_call=SimpleNamespace(call_id=action_id)),case['id'],note)
        assert result['id']==case['id']
        item={'id':action_id+'-reply','text':'I have added the address correction note about the location being between 17th and 18th again. Let me know if you need help with anything else.'}
        saved=await client.post('/calls/'+call_id+'/transcript',json={**item,'role':'assistant','action_ids':assistant.take_note_actions()})
        assert saved.status_code==200
        assert saved.json()['confirmed_actions'][0]['action_id']==action_id
        assert assistant.take_note_actions()==[]
    payloads=[]
    async def false_verdict(payload):
        import json
        payloads.append(json.loads(payload))
        return supervision.ModelVerdict(violation='unsupported_save',evidence=item['text'])
    monkeypatch.setattr(supervision,'configured',lambda:True)
    monkeypatch.setattr(supervision,'_model_verdict',false_verdict)
    await agent.inspect_and_correct(client,speaker,call_id,item,set(),lambda:False)
    assert speaker.spoken==[]
    finding=(await client.get('/calls/'+call_id)).json()['supervisor_reviews'][0]
    assert finding['status']=='checked' and 'receipt' in finding['reason']
    assert [a['action_id'] for a in payloads[0]['confirmed_actions']]==['requested-repeat']
    assert len((await client.get('/cases/'+case['id'])).json()['notes'])==2


@pytest.mark.asyncio
async def test_receipts_cannot_be_invented_borrowed_or_changed_on_replay(context):
    client,call_id,case=context
    body={'id':'receipt-reply','role':'assistant','text':'I added your note.','action_ids':['note-action']}
    assert (await client.post('/calls/'+call_id+'/transcript',json=body)).status_code==409
    await client.patch('/cases/'+case['id'],json={'call_id':call_id,'action_id':'note-action','note':'The bin is still outside.'})
    assert (await client.post('/calls/'+call_id+'/transcript',json=body)).status_code==200
    assert (await client.post('/calls/'+call_id+'/transcript',json=body)).status_code==200
    assert (await client.post('/calls/'+call_id+'/transcript',json={**body,'action_ids':[]})).status_code==409
    other=(await client.post('/calls/test')).json()['id']
    await client.get('/cases/lookup',params={'call_id':other,'case_id':case['id']})
    assert (await client.post('/calls/'+other+'/transcript',json=body)).status_code==409
    assert (await client.post('/calls/'+call_id+'/transcript',json={**body,'id':'user-receipt','role':'user'})).status_code==409
