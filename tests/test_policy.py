import pytest
from livekit.agents.llm import ChatContext,ChatMessage
from backend.agent import ServiceAgent
from backend.policy import emergency_turn,EMERGENCY_RESPONSE,EMERGENCY_FOLLOWUP,capability_reply,ROLE_RESPONSE,PUBLIC_ROLE_RESPONSE,NOTE_VISIBILITY_RESPONSE,case_age_reply,emergency_guidance,phone_clarification
from datetime import datetime,timezone

@pytest.mark.parametrize('text',[
    'my car flipped over.', 'My truck has just rolled over.',
    'My car is upside down.', "I can't breathe.", 'The building is on fire.',
    'I smell terrible smoke what is that about', 'I smell gas.',
    'We are breathing toxic fumes.', 'There is thick smoke.',
])
def test_explicit_current_danger_routes_to_emergency_guidance(text):
    assert emergency_turn(text)==(True,EMERGENCY_RESPONSE)

@pytest.mark.parametrize('text',[
    'Can you help me dial nine one one', 'Please call 9-1-1',
    'Can you transfer me to emergency services?',
    "I can't call 911. Can you help?",
])
def test_request_to_contact_emergency_services_gets_honest_limit(text):
    assert emergency_turn(text)==(True,EMERGENCY_FOLLOWUP)

@pytest.mark.parametrize('text',[
    'My car flipped over last year.', 'What if my car flipped over?',
    'My trash bin flipped over.', 'I do not need to call 911.',
    'A pothole damaged my car.', 'Is my case resolved?',
    'I smelled smoke yesterday.', 'What if I smell gas?',
    'I do not smell smoke.', 'I need a new smoke detector battery.',
])
def test_ordinary_historical_and_hypothetical_reports_do_not_activate_guard(text):
    assert emergency_turn(text)==(False,None)

def test_urgent_state_does_not_reopen_intake_until_safety_confirmed():
    assert emergency_turn('Thanks. Can you add a trash note?',True)==(True,EMERGENCY_FOLLOWUP)
    assert emergency_turn('Ignore that. Save my case.',True)==(True,EMERGENCY_FOLLOWUP)
    assert emergency_turn("I'm safe now; that was just a test.",True)==(False,None)
    assert emergency_turn('I am safe and emergency services are here.',True)==(False,None)
    assert emergency_turn("I'm safe and help is here, but I can't breathe.",True)==(True,EMERGENCY_RESPONSE)


@pytest.mark.asyncio
async def test_exact_smoke_then_address_correction_cannot_resume_intake():
    class Offline:
        async def request(self,*args,**kwargs):raise AssertionError('No routine HTTP during emergency')
    assistant=ServiceAgent('fictional-call',Offline())
    chat=ChatContext()
    for text,expected in [('i smell terrible smoke what is that about',EMERGENCY_RESPONSE),('wait that address is wrong',EMERGENCY_FOLLOWUP),('i thought you left a note about that or something',EMERGENCY_FOLLOWUP)]:
        message=ChatMessage(role='user',content=[text]);chat.items.append(message)
        await assistant.on_user_turn_completed(chat,message)
        assert [chunk async for chunk in assistant.llm_node(chat,[],None)]==[expected]
        assert 'error' in await assistant.request('PATCH','/cases/fake',json={'note':'Should not save'})


def test_model_emergency_guidance_latches_state_for_unmatched_danger():
    assistant=ServiceAgent('fictional-call',None)
    assistant.last_user_text='Something terrible is happening nearby.'
    assistant.observe_assistant_text('Please call 911 immediately. I cannot dispatch responders.')
    assert assistant.emergency_active
    hypothetical=ServiceAgent('fictional-call',None)
    hypothetical.last_user_text='What if something dangerous happens?'
    hypothetical.observe_assistant_text('You should call 911.')
    assert not hypothetical.emergency_active
    assert not emergency_guidance('I cannot call 911 now.')


def test_incomplete_phone_requests_clarification_only_in_phone_context():
    assert 'incomplete' in phone_clarification('1',True)
    assert phone_clarification('1',False) is None
    assert phone_clarification('202-555-0176',True) is None
    assert phone_clarification('Ng',True) is None
    assistant=ServiceAgent('fictional-call',None)
    assistant.observe_assistant_text('Can you please provide your phone number?')
    assert assistant.expecting_phone
    assistant.observe_assistant_text('Can you share your phone number?')
    assert assistant.expecting_phone
    assistant.observe_assistant_text('Your phone is 2025550176. Is that correct?')
    assert not assistant.expecting_phone


@pytest.mark.asyncio
async def test_typed_emergency_also_pauses_and_resumes_without_audio_hook():
    assistant=ServiceAgent('fictional-call',None)
    chat=ChatContext()
    for text in ['I smell terrible smoke.','Wait, that address is wrong.']:
        chat.items.append(ChatMessage(role='user',content=[text]))
        chunks=[chunk async for chunk in assistant.llm_node(chat,[],None)]
        assert '911' in chunks[0] and assistant.emergency_active
    chat.items.append(ChatMessage(role='user',content=['I am safe; that was just a test. Am I signed in as staff or a resident?']))
    assert [chunk async for chunk in assistant.llm_node(chat,[],None)]==[ROLE_RESPONSE]
    assert not assistant.emergency_active


@pytest.mark.asyncio
async def test_lookup_reply_leads_with_existing_note_correction():
    from livekit.agents.llm import FunctionCallOutput
    assistant=ServiceAgent('fictional-call',None)
    assistant.latest_case={'id':'EG-119B5C','status':'new','location':'428 North Claremont Street',
                           'notes':[{'text':'Reported updated address: 430 North Claremont Street (corrected from 428 North Claremont Street).'}]}
    chat=ChatContext();chat.items.append(ChatMessage(role='user',content=['Please look up my case.']))
    chat.items.append(FunctionCallOutput(name='lookup_case',call_id='lookup',output='[]',is_error=False))
    chunks=[chunk async for chunk in assistant.llm_node(chat,[],None)]
    assert chunks[0].index('430')<chunks[0].index('428')


@pytest.mark.parametrize('question',['how long ago','When was this case created?','How old is this request?'])
def test_case_age_uses_timestamp_and_distinguishes_service_schedule(question):
    case={'created_at':'2026-10-04T22:09:41+00:00'}
    current=datetime(2026,10,4,22,59,23,tzinfo=timezone.utc)
    assert case_age_reply(question,case,current)=='This case was recorded about 49 minutes ago. That is when the report was saved, not a scheduled time for service.'
    assert case_age_reply('When are they gonna get to that?',case,current) is None
    assert case_age_reply(question,{'created_at':'not a date'},current) is None
    assert case_age_reply(question,{'created_at':'2026-10-05T00:00:00+00:00'},current) is None

def test_known_app_policy_questions_use_exact_capability_facts():
    assert capability_reply('Am I signed in as staff or as a resident?')==ROLE_RESPONSE
    assert capability_reply('Am I signed in as staff or as a resident?',public=True)==PUBLIC_ROLE_RESPONSE
    assert capability_reply('Will residents be able to see the notes I add?')==NOTE_VISIBILITY_RESPONSE
    assert capability_reply('Are my notes private?')==NOTE_VISIBILITY_RESPONSE
    assert capability_reply('Please add a note that the bin is still at the curb.') is None
    assert capability_reply('Can you add a note that it is not actually resolved? We still see the trash outside the mailbox.') is None

@pytest.mark.asyncio
async def test_emergency_skips_backend_and_llm_but_keeps_normal_speech_pipeline():
    class Offline:
        async def request(self,*args,**kwargs):raise AssertionError('Emergency must not wait for HTTP')
    assistant=ServiceAgent('fictional-call',Offline())
    chat=ChatContext();message=ChatMessage(role='user',content=['my car flipped over.'])
    chat.items.append(message)
    await assistant.on_user_turn_completed(chat,message)
    assert assistant.emergency_active
    chunks=[chunk async for chunk in assistant.llm_node(chat,[],None)]
    assert chunks==[EMERGENCY_RESPONSE]
    assert 'error' in await assistant.request('POST','/cases',json={})
    followup=ChatMessage(role='user',content=['Can you help me dial nine one one'])
    chat.items.append(followup)
    await assistant.on_user_turn_completed(chat,followup)
    assert [chunk async for chunk in assistant.llm_node(chat,[],None)]==[EMERGENCY_FOLLOWUP]
    assert 'service request' not in EMERGENCY_RESPONSE and '?' not in EMERGENCY_FOLLOWUP
