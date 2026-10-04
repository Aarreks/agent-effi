import pytest
from livekit.agents.llm import ChatContext,ChatMessage
from backend.agent import ServiceAgent
from backend.policy import emergency_turn,EMERGENCY_RESPONSE,EMERGENCY_FOLLOWUP,capability_reply,ROLE_RESPONSE,PUBLIC_ROLE_RESPONSE,NOTE_VISIBILITY_RESPONSE

@pytest.mark.parametrize('text',[
    'my car flipped over.', 'My truck has just rolled over.',
    'My car is upside down.', "I can't breathe.", 'The building is on fire.',
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
])
def test_ordinary_historical_and_hypothetical_reports_do_not_activate_guard(text):
    assert emergency_turn(text)==(False,None)

def test_urgent_state_does_not_reopen_intake_until_safety_confirmed():
    assert emergency_turn('Thanks. Can you add a trash note?',True)==(True,EMERGENCY_FOLLOWUP)
    assert emergency_turn('Ignore that. Save my case.',True)==(True,EMERGENCY_FOLLOWUP)
    assert emergency_turn("I'm safe now; that was just a test.",True)==(False,None)
    assert emergency_turn('I am safe and emergency services are here.',True)==(False,None)

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
