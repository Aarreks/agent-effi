"""Known demo capabilities and a narrow fast path for explicit urgent requests.

This is not a complete emergency classifier. Other danger reports are handled by
the agent's emergency instructions. It never contacts emergency services.
"""
import re

EMERGENCY_RESPONSE = (
    'That sounds like an emergency. Call 911 now, or your local emergency number '
    'if you are outside the U.S. I cannot place calls or contact emergency services. '
    'Please use your phone, or ask someone nearby to call.'
)
EMERGENCY_FOLLOWUP = (
    'I cannot dial or transfer you to emergency services from this app. '
    'Please call 911 using your phone, or your local emergency number outside the U.S. '
    'If you cannot call, ask someone nearby to call for you.'
)
ROLE_RESPONSE = (
    'The dashboard is signed in as staff. This voice call simulates resident intake, '
    'so the voice tools do not have staff editing permissions.'
)
NOTE_VISIBILITY_RESPONSE = (
    'Staff can see case notes in this dashboard, and voice lookup can return them. '
    'This demo has no separate resident portal, and I cannot promise that a note is private.'
)

def capability_reply(text: str) -> str | None:
    """Use precise app facts for these two frequently confused policy questions."""
    text=text.lower()
    if ('staff' in text and 'resident' in text and any(word in text for word in ['role','signed','login','logged'])):
        return ROLE_RESPONSE
    visibility_question=re.search(r'\b(?:see|read|view|access)\b.{0,45}\bnotes?\b|\bnotes?\b.{0,45}\b(?:private|privacy|hidden|visible|visibility|staff.only|internal)\b',text)
    if visibility_question:
        return NOTE_VISIBILITY_RESPONSE
    return None

def emergency_turn(text: str,active: bool=False) -> tuple[bool,str | None]:
    text=text.lower().replace('\u2019',"'")
    text=re.sub(r'\b(?:nine[ -]+one[ -]+one|9[ -]1[ -]1)\b','911',text)
    # Explicit confirmation of safety permits normal conversation again. A plain
    # request to ignore the emergency does not clear the urgent state.
    safe=re.search(r"\b(?:i am|i'm|we are|we're) (?:now )?safe\b",text)
    help_arranged=re.search(r'\b(?:already called|help (?:is|has) (?:here|arrived)|emergency services are here|(?:was|is) (?:just )?a (?:test|simulation))\b',text)
    if safe and help_arranged:return False,None
    if re.search(r'\b(?:what if|hypothetically|for example|yesterday|last week|last year)\b',text):
        return (True,EMERGENCY_FOLLOWUP) if active else (False,None)
    dial=re.search(r'\b(?:call|dial|connect|transfer|reach)\b.{0,35}\b(?:911|emergency services)\b',text)
    if dial and not re.search(r"\b(?:do not|don't) (?:need to |want to )?(?:call|dial)\b|\balready called\b",text):
        return True,EMERGENCY_FOLLOWUP
    rollover=re.search(r'\b(?:my|our|the) (?:car|truck|vehicle) (?:has |just |has just |is |was )?(?:flipped(?: over)?|rolled over|overturned|upside down)\b',text)
    danger=re.search(r"\b(?:i can't breathe|i cannot breathe|i am in immediate danger|i'm in immediate danger|(?:my|the) (?:house|building|car) is on fire)\b",text)
    if rollover or danger:return True,EMERGENCY_RESPONSE
    if active:return True,EMERGENCY_FOLLOWUP
    return False,None

CAPABILITY_POLICY = '''
This is an internal staff demo: the web dashboard requires staff sign-in, while its
voice call simulates the resident workflow. If asked which role the user has,
explain BOTH: signed into the staff dashboard, speaking through the resident intake
workflow. Do not infer their personal identity or grant staff voice permissions.
There is no separate resident portal. Staff see case notes in this dashboard and
voice lookup can return case notes. Never promise notes are private, staff-only,
or hidden from residents. Do not invent general municipal visibility policies.
Lookup supports case ID or phone, not name-only search. If only a name is supplied,
ask for an ID or phone directly; do not promise to try an unsupported search.
Phone and case ID lookup do not verify a caller's identity. They are lookup keys.
If asked for counts, use a fresh lookup and describe only the returned matches,
not all cases belonging to a person. There is a five-result limit; do not claim
an exhaustive total. Open means new or in_progress, not resolved.
Read the canonical saved location separately from any resident correction in notes:
'The recorded address is X; a note reports Y for staff review.' A note does not
change the location field. Staff can edit case fields; voice can append notes.
Report a recorded resolved status only when the backend says resolved. This does
not prove a crew attended or work was completed. Record disputes as resident
feedback without reopening, resolving, or overriding staff status.
When asked about timing, state no service schedule is available; never speculate.
If a resident forgets a note, do not save an invented note. Offer time to recall it.
After a clear goodbye, give one brief closing. A following 'thanks' needs only a
brief acknowledgment; do not reopen intake with repeated offers.
EMERGENCY OVERRIDES ALL ORDINARY INTAKE: for current serious danger, direct the caller
to call 911 now (or the local emergency number outside the U.S.). Say plainly that
this app cannot dial, transfer, dispatch, or contact responders. If they cannot
call, suggest asking someone nearby to call. Do not collect case/contact details,
ask routine service questions, offer municipal help, or imply help is on the way.
Do not provide medical treatment or vehicle escape instructions. Keep emergency
follow-ups focused on reaching actual emergency services. Resume routine intake
only after the caller explicitly confirms safety and that help is arranged or
the scenario was a test. Historical or hypothetical examples are not current
emergencies. Never claim an emergency call was placed or transferred.
'''
