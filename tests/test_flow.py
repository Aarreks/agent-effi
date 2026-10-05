from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.store import Store


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path/'test.sqlite3'))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('VOICE_PROVIDER','openai')
    with TestClient(main.app) as client:
        assert client.post('/auth/login',json={'password':'test-staff-password'}).status_code==200
        yield client


def new_call(client):
    return client.post('/calls/test').json()['id']


def test_lookup_switch_to_new_report_collects_new_identity(client):
    original=report(client).json()
    call_id=new_call(client)
    assert client.get('/cases/lookup',params={'call_id':call_id,'case_id':original['id']}).status_code==200
    response=client.patch('/calls/'+call_id+'/intake',json={'start_new':True})
    assert response.status_code==200
    assert response.json()['case_id'] is None and response.json()['intake']=={}
    details=dict(name='Troy Zhang',phone='8427892014',issue_type='other',description='Broken traffic light',location='67 Carousel Street')
    draft=client.patch('/calls/'+call_id+'/intake',json=details).json()
    assert draft['intake']==details
    saved=client.post('/cases',json={'call_id':call_id,**details})
    assert saved.status_code==201 and saved.json()['name']=='Troy Zhang' and saved.json()['phone']=='8427892014'
    assert saved.json()['id']!=original['id']
    assert client.get('/cases/'+original['id']).json()['name']==original['name']
    assert client.get('/cases/'+original['id']).json()['notes']==original['notes']
    assert client.patch('/calls/'+call_id+'/intake',json={'start_new':True}).status_code==409


def test_cannot_reset_intake_after_call_ends(client):
    call_id=new_call(client)
    client.post('/calls/'+call_id+'/finish')
    assert client.patch('/calls/'+call_id+'/intake',json={'start_new':True}).status_code==409


def report(client,call_id=None,**fields):
    return client.post('/cases',json=dict(call_id=call_id or new_call(client),name='Jordan Lee',phone='(415) 555-0134',
                    issue_type='missed_collection',description='Trash was not collected this morning.',location='24 Cedar Avenue',**fields))


def test_end_to_end_case_and_followup(client):
    first_call=new_call(client)
    case=report(client,first_call).json()
    assert client.get('/calls/'+first_call).json()['case_id']==case['id']
    assert client.get('/cases').json()[0]['name']=='Jordan Lee'
    staff=client.patch('/cases/'+case['id'],json={'revision':1,'status':'in_progress','note':'Sent to sanitation review.'})
    assert staff.status_code==200
    second_call=new_call(client)
    found=client.get('/cases/lookup',params={'call_id':second_call,'phone':'+1 415 555 0134'}).json()
    assert found[0]['status']=='in_progress'
    note={'call_id':second_call,'action_id':'tool-42','note':'The bin is still at the curb.'}
    added=client.patch('/cases/'+case['id'],json=note).json()
    replay=client.patch('/cases/'+case['id'],json=note).json()
    assert replay==added and len(replay['notes'])==2
    detail=client.get('/cases/'+case['id']).json()
    assert len(detail['audit'])==3 and detail['audit'][-1]['actor']=='voice'
    assert client.get('/cases?status=in_progress&search=Cedar').json()[0]['id']==case['id']


def test_creation_retries_are_atomic(client):
    call_id=new_call(client)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:report(client,call_id).json(),range(6)))
    assert len({c['id'] for c in results})==1
    assert len(client.get('/cases').json())==1


def test_changed_create_and_lookup_then_create_do_not_falsely_succeed(client):
    call_id=new_call(client)
    case=report(client,call_id).json()
    changed=dict(call_id=call_id,name='Jordan Lee',phone='4155550134',issue_type='streetlight',description='A streetlight is out.',location='Cedar Avenue')
    assert client.post('/cases',json=changed).status_code==409
    another_call=new_call(client)
    client.get('/cases/lookup',params={'call_id':another_call,'case_id':case['id']})
    assert client.post('/cases',json={**changed,'call_id':another_call}).status_code==409
    assert len(client.get('/cases').json())==1


def test_switching_linked_case_cannot_replay_creation_as_another_case(client):
    first_call=new_call(client)
    first=report(client,first_call).json()
    second=report(client).json()
    client.get('/cases/lookup',params={'call_id':first_call,'case_id':second['id']})
    assert report(client,first_call).status_code==409
    assert first['id'] != second['id']


def test_invalid_creation_does_not_link_call(client):
    call_id=new_call(client)
    response=client.post('/cases',json={'call_id':call_id,'name':'   ','phone':'not-a-phone','issue_type':'pothole','description':'ok'})
    assert response.status_code==422
    assert client.get('/calls/'+call_id).json()['case_id'] is None
    assert client.get('/cases').json()==[]


def test_stale_staff_revision_does_not_overwrite(client):
    case=report(client).json()
    path='/cases/'+case['id']
    assert client.patch(path,json={'revision':1,'status':'resolved'}).status_code==200
    assert client.patch(path,json={'revision':1,'status':'new'}).status_code==409
    assert client.get(path).json()['status']=='resolved'


def test_voice_cannot_change_staff_status_or_unknown_case(client):
    case=report(client).json();call_id=new_call(client)
    path='/cases/'+case['id']
    assert client.patch(path,json={'call_id':call_id,'note':'Guessing a case'}).status_code==409
    client.get('/cases/lookup',params={'call_id':call_id,'case_id':case['id']})
    assert client.patch(path,json={'call_id':call_id,'status':'resolved'}).status_code==422
    assert client.patch(path,json={'call_id':call_id,'note':'More details','action_id':'x'}).status_code==200
    assert client.patch(path,json={'call_id':call_id,'note':'Different content','action_id':'x'}).status_code==409


def test_ambiguous_phone_requires_case_selection(client):
    a=report(client).json();b=report(client).json();call_id=new_call(client)
    assert len(client.get('/cases/lookup',params={'call_id':call_id,'phone':'4155550134'}).json())==2
    assert client.get('/calls/'+call_id).json()['case_id'] is None
    client.get('/cases/lookup',params={'call_id':call_id,'case_id':b['id'].lower()})
    assert client.get('/calls/'+call_id).json()['case_id']==b['id']


def test_spoken_case_spacing_and_explicit_id_take_precedence(client):
    a=report(client).json();report(client);call_id=new_call(client)
    spoken=' '.join(a['id'].replace('-','').lower())
    matches=client.get('/cases/lookup',params={'call_id':call_id,'case_id':spoken,'phone':'4155550134'}).json()
    assert len(matches)==1 and matches[0]['id']==a['id']
    assert client.get('/cases/lookup',params={'call_id':call_id,'case_id':'EG-UNKNOWN','phone':'4155550134'}).json()==[]


def test_transcript_replay_and_unconfigured_analysis(client):
    call_id=new_call(client);path='/calls/'+call_id
    turn={'id':'utterance-1','role':'user','text':'My trash was missed.'}
    assert client.post(path+'/transcript',json=turn).status_code==200
    assert client.post(path+'/transcript',json=turn).status_code==200
    assert client.post(path+'/transcript',json={**turn,'text':'Something else'}).status_code==409
    assert len(client.get(path).json()['transcript'])==1
    client.post(path+'/finish')
    finished=client.get(path).json()
    assert finished['status']=='ended' and finished['analysis_status']=='unavailable'
    assert finished['analysis'] is None
    first_end=finished['ended_at']
    client.post(path+'/finish')
    assert client.get(path).json()['ended_at']==first_end


def test_restart_preserves_data(client,monkeypatch):
    case=report(client).json();call_id=client.get('/calls').json()[0]['id']
    client.post('/calls/'+call_id+'/transcript',json={'id':'x','role':'assistant','text':'Your request was recorded.'})
    path=main.store.path
    monkeypatch.setattr(main,'store',Store(path))
    assert client.get('/cases/'+case['id']).json()['id']==case['id']
    assert len(client.get('/calls/'+call_id).json()['transcript'])==1


def test_websocket_notifies_after_commit(client):
    with client.websocket_connect('/events') as ws:
        assert ws.receive_json()['type']=='connected'
        call_id=new_call(client)
        assert ws.receive_json()=={'type':'call','id':call_id}
        case=report(client,call_id).json()
        assert ws.receive_json()=={'type':'case','id':case['id']}
        assert client.get('/cases/'+case['id']).status_code==200


def test_voice_rejects_missing_credentials_without_fake_call(client):
    assert client.post('/voice/session').status_code==503
    assert client.get('/calls').json()==[]


def test_analysis_is_separate_from_staff_fields(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-not-a-real-key')
    async def fake_analysis(transcript):
        return {'summary':'Resident reported missed trash.','caller_name':'Wrong name','phone':None,'issue_type':'other','location':None,'outcome':'Recorded for review','follow_up':['Review collection route']}
    monkeypatch.setattr(main,'analyze',fake_analysis)
    case=report(client).json();call_id=client.get('/calls').json()[0]['id']
    client.post('/calls/'+call_id+'/finish')
    assert client.get('/calls/'+call_id).json()['analysis_status']=='complete'
    assert client.get('/cases/'+case['id']).json()['name']=='Jordan Lee'


def test_analysis_failure_is_visible_and_retryable(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-not-a-real-key')
    async def fail(transcript): raise TimeoutError('provider unavailable')
    monkeypatch.setattr(main,'analyze',fail)
    call_id=new_call(client)
    client.post('/calls/'+call_id+'/finish')
    assert client.get('/calls/'+call_id).json()['analysis_status']=='failed'
    assert client.post('/calls/'+call_id+'/analyze').status_code==200


def test_live_intake_merges_corrects_and_requires_confirmation_before_case(client):
    call_id=new_call(client);path='/calls/'+call_id+'/intake'
    assert client.patch(path,json={'issue_type':'other','description':'Something is wrong with the street.'}).status_code==200
    assert client.get('/cases').json()==[]
    fields={'issue_type':'streetlight','name':'Jordan Lee','stage':'awaiting_confirmation'}
    first=client.patch(path,json=fields).json()
    replay=client.patch(path,json=fields).json()
    assert first==replay and len(replay['intake_history'])==2
    assert replay['intake']['description']=='Something is wrong with the street.'
    assert replay['intake']['issue_type']=='streetlight' and replay['case_id'] is None
    client.post('/calls/'+call_id+'/finish')
    assert client.patch(path,json={'name':'Someone else'}).status_code==409


def test_supervisor_corrections_are_linked_durable_and_retry_safe(client,monkeypatch):
    case=report(client).json();call_id=client.get('/calls').json()[0]['id'];path='/calls/'+call_id
    utterance='Your case is resolved.'
    review={'event_id':'claim-1','status':'corrected','utterance':utterance,'reason':'Case remains new.','correction':'Your request is recorded and awaiting staff review.'}
    assert client.post(path+'/supervisor',json=review).status_code==409
    client.post(path+'/transcript',json={'id':'claim-1','role':'assistant','text':utterance})
    first=client.post(path+'/supervisor',json=review).json()
    assert client.post(path+'/supervisor',json=review).json()==first
    assert len(first['supervisor_reviews'])==1 and first['supervisor_status']=='needs_attention'
    assert client.post(path+'/supervisor',json={**review,'correction':'Changed correction'}).status_code==409
    monkeypatch.setattr(main,'store',Store(main.store.path))
    assert client.get(path).json()['supervisor_reviews'][0]['correction']==review['correction']
    assert client.get('/cases/'+case['id']).json()['status']=='new'


def test_supervisor_grounding_preserves_status_at_the_spoken_turn(client):
    case=report(client).json();call_id=client.get('/calls').json()[0]['id'];path='/calls/'+call_id
    turn={'id':'status-1','role':'assistant','text':'Your request is awaiting staff review.'}
    saved=client.post(path+'/transcript',json=turn).json()
    client.patch('/cases/'+case['id'],json={'revision':1,'status':'resolved'})
    assert client.post(path+'/transcript',json=turn).json()==saved
    assert client.get(path).json()['transcript'][0]['case_snapshot']['status']=='new'


def test_live_caption_is_temporary_and_not_a_transcript_duplicate(client):
    call_id=new_call(client);path='/calls/'+call_id
    with client.websocket_connect('/events') as ws:
        ws.receive_json()
        client.post(path+'/caption',json={'role':'user','text':'My trash was'})
        assert ws.receive_json()=={'type':'caption','id':call_id}
        call=client.get(path).json()
        assert call['live_caption']['text']=='My trash was' and call['transcript']==[]
        client.post(path+'/caption',json={'role':'user','text':'My trash was missed.'})
        assert ws.receive_json()['type']=='caption'
        client.post(path+'/transcript',json={'id':'turn-1','role':'user','text':'My trash was missed.'})
        assert ws.receive_json()['type']=='transcript'
        call=client.get(path).json()
        assert call['live_caption'] is None and len(call['transcript'])==1
        client.post(path+'/caption',json={'role':'user','text':'Another detail'})
        assert ws.receive_json()['type']=='caption'
        client.post(path+'/transcript',json={'id':'turn-1','role':'user','text':'My trash was missed.'})
        assert ws.receive_json()['type']=='transcript'
        assert client.get(path).json()['live_caption']['text']=='Another detail'
    client.post(path+'/finish')
    assert client.post(path+'/caption',json={'role':'user','text':'late text'}).status_code==409
