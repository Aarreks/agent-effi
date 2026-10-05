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


def test_worker_starts_next_report_only_within_its_call(staff):
    call_id=staff.post('/calls/test').json()['id'];other=staff.post('/calls/test').json()['id']
    fields=dict(call_id=call_id,name='Morgan Example',phone='2025550149',issue_type='pothole',description='First pothole',location='24 Cedar Avenue')
    first=staff.post('/cases',json=fields).json()
    staff.cookies.clear();staff.headers.update({'Authorization':'Bearer '+'w'*32,'X-Call-ID':call_id})
    assert staff.post('/calls/'+other+'/new-intake',json={'action_id':'cross'}).status_code==403
    reset=staff.post('/calls/'+call_id+'/new-intake',json={'action_id':'own-reset'})
    assert reset.status_code==200
    assert staff.get('/cases/'+first['id']).status_code==403
    second=staff.post('/cases',json={**fields,'intake_id':reset.json()['intake_id'],'description':'Second pothole'}).json()
    assert second['id']!=first['id']
    assert staff.get('/cases/'+second['id']).status_code==200
    assert staff.get('/calls/'+call_id).json()['case_ids']==[first['id'],second['id']]


@pytest.mark.parametrize('creations,updates',[(1,3),(2,4),(4,2)])
def test_worker_interleaves_new_reports_and_existing_case_updates(staff,creations,updates):
    fields=dict(name='Morgan Example',phone='2025550149',issue_type='pothole',description='Existing pothole',location='24 Cedar Avenue')
    existing=[]
    for _ in range(2):
        seed_call=staff.post('/calls/test').json()['id']
        existing.append(staff.post('/cases',json={'call_id':seed_call,**fields}).json()['id'])
    call_id=staff.post('/calls/test').json()['id']
    staff.cookies.clear();staff.headers.update({'Authorization':'Bearer '+'w'*32,'X-Call-ID':call_id})
    created=[];linked=[];expected={case_id:[] for case_id in existing}
    for index in range(max(creations,updates)):
        if index<creations:
            reset=staff.post('/calls/'+call_id+'/new-intake',json={'action_id':f'reset-{index}'})
            assert reset.status_code==200
            body={'call_id':call_id,'intake_id':reset.json()['intake_id'],**fields,'description':f'New report {index}'}
            response=staff.post('/cases',json=body)
            assert response.status_code==201
            case=response.json();created.append(case['id']);linked.append(case['id'])
            assert staff.post('/cases',json=body).json()==case
        if index<updates:
            target=existing[index%2]
            found=staff.get('/cases/lookup',params={'call_id':call_id,'case_id':target})
            assert found.status_code==200 and found.json()[0]['id']==target
            if target not in linked:linked.append(target)
            note=f'Confirmed follow-up {index}'
            body={'call_id':call_id,'action_id':f'note-{index}','note':note}
            response=staff.patch('/cases/'+target,json=body)
            assert response.status_code==200
            assert staff.patch('/cases/'+target,json=body).json()==response.json()
            assert staff.patch('/cases/'+target,json={**body,'note':'Changed retry'}).status_code==409
            expected[target].append(note)
    assert staff.get('/calls/'+call_id).json()['case_ids']==linked
    assert len(set(created))==creations
    # Revisit earlier cases under worker permissions; switching must preserve all writes.
    for case_id in created+existing:
        assert staff.get('/cases/lookup',params={'call_id':call_id,'case_id':case_id}).status_code==200
        saved=staff.get('/cases/'+case_id).json()
        if case_id in expected:
            assert [note['text'] for note in saved['notes']]==expected[case_id]
            assert all(note['call_id']==call_id for note in saved['notes'])
            assert saved['revision']==1+len(expected[case_id])
        else:
            assert saved['description']==f'New report {created.index(case_id)}'
            assert saved['revision']==1 and saved['notes']==[]
    staff.headers.clear()
    assert staff.post('/auth/login',json={'password':'test-staff-password'}).status_code==200
    assert len(staff.get('/cases').json())==2+creations
