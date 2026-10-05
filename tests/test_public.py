import pytest
from fastapi.testclient import TestClient
from backend import auth, main
from backend.store import Store


@pytest.fixture
def public_client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path/'public.sqlite3'))
    main.public_starts.clear()
    with TestClient(main.app) as client:
        yield client


def test_resident_capability_is_bound_expiring_and_never_staff():
    first='11111111-1111-4111-8111-111111111111'
    second='22222222-2222-4222-8222-222222222222'
    token=auth.resident_token(first,now=1000)
    assert auth.verify_resident('Bearer '+token,first,now=1001)
    assert not auth.verify_resident('Bearer '+token,second,now=1001)
    assert not auth.verify_resident('Bearer '+token,first,now=4600)
    assert not auth.verify_resident('Bearer '+token,first,now=999)
    assert not auth.verify_resident('Bearer '+token[:-1]+('0' if token[-1]!='0' else '1'),first,now=1001)
    assert not auth.verify_staff(token,now=1001)
    assert not auth.verify_worker('Bearer '+token)


def test_public_call_projection_and_access_boundary(public_client):
    first=main.store.start_call();other=main.store.start_call()
    case=main.store.create_case(first['id'],dict(name='Resident',phone='2025550199',issue_type='pothole',description='A large pothole.',location='42 Oak Street'))
    main.store.patch_case(case['id'],{'note':'Staff-only API field'},actor='staff')
    main.store.turn(first['id'],'assistant-turn','assistant','Your case was recorded.')
    token=auth.resident_token(first['id']);headers={'Authorization':'Bearer '+token}
    path='/public/calls/'+first['id']
    assert public_client.get(path).status_code==401
    response=public_client.get(path,headers=headers)
    assert response.status_code==200
    data=response.json()
    assert data['receipt']=={key:case[key] for key in ['id','status','issue_type','location']}
    assert 'case_snapshot' not in data['transcript'][0]
    assert 'Staff-only API field' not in response.text
    assert all(key not in data for key in ['analysis','supervisor_reviews','intake_history'])
    for method,url in [('GET','/public/calls/'+other['id']),('POST','/public/calls/'+other['id']+'/finish'),('PATCH',path),('POST',path+'/transcript'),('GET','/cases'),('GET','/calls'),('PATCH','/cases/'+case['id']),('GET','/calls/'+first['id'])]:
        assert public_client.request(method,url,headers=headers).status_code==401
    assert public_client.get(path,headers={**headers,'Origin':'https://untrusted.example'}).status_code==403


def test_public_finish_only_ends_its_call(public_client,monkeypatch):
    first=main.store.start_call();other=main.store.start_call()
    async def no_analysis(call_id):pass
    monkeypatch.setattr(main,'finish_analysis',no_analysis)
    headers={'Authorization':'Bearer '+auth.resident_token(first['id'])}
    assert public_client.post('/public/calls/'+first['id']+'/finish',headers=headers).json()=={'ended':True}
    assert main.store.call(first['id'])['status']=='ended'
    assert main.store.call(other['id'])['status']=='connecting'


def test_public_session_needs_no_staff_cookie_and_is_rate_limited(public_client,monkeypatch):
    async def session(public=False):
        assert public
        return {'call_id':'example','access_token':'example'}
    monkeypatch.setattr(main,'start_voice_session',session)
    assert public_client.post('/public/voice/session',headers={'Origin':'https://untrusted.example'}).status_code==403
    for _ in range(5):assert public_client.post('/public/voice/session').status_code==201
    assert public_client.post('/public/voice/session').status_code==429
    assert public_client.post('/voice/session').status_code==401


def test_public_confirmation_preserves_both_cases_without_private_fields(public_client):
    call=main.store.start_call('test')
    fields=dict(name='Morgan Example',phone='2025550149',issue_type='pothole',description='First pothole',location='24 Cedar Avenue')
    first=main.store.create_case(call['id'],fields)
    main.store.update_intake(call['id'],{},start_new=True,reset_id='public-reset')
    second=main.store.create_case(call['id'],{**fields,'description':'Second pothole','location':'70 Maple Road'})
    main.store.patch_case(first['id'],{'note':'Private staff note'},actor='staff')
    headers={'Authorization':'Bearer '+auth.resident_token(call['id'])}
    response=public_client.get('/public/calls/'+call['id'],headers=headers)
    assert response.status_code==200
    data=response.json()
    assert [receipt['id'] for receipt in data['receipts']]==[first['id'],second['id']]
    assert data['receipt']['id']==second['id']
    assert 'Private staff note' not in response.text
    assert all(set(receipt)<={'id','status','issue_type','location','reported_correction'} for receipt in data['receipts'])
