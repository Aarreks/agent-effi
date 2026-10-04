"""Known demo capabilities and a narrow fast path for explicit urgent requests.

This is not a complete emergency classifier. Other danger reports are handled by
the agent's emergency instructions. It never contacts emergency services.
"""
import re
from datetime import datetime, timezone

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
PUBLIC_ROLE_RESPONSE = (
    'You are using the public resident demo. No staff sign-in is needed to report '
    'an issue here. Staff editing permissions are only available in the separate staff workspace.'
)
NOTE_VISIBILITY_RESPONSE = (
    'Staff can see case notes in this dashboard, and voice lookup can return them. '
    'The public reporting page shows only its own call and a case confirmation. '
    'I cannot promise that a note is private.'
)

def historical_or_hypothetical(text: str) -> bool:
    return bool(re.search(r'\b(?:what if|hypothetically|for example|yesterday|last (?:night|week|year)|earlier today)\b',text.lower()))


def emergency_guidance(text: str) -> bool:
    """Recognize an actual direction to call for help, not a claim that we can dial."""
    text=text.lower()
    for match in re.finditer(r'\b(?:please |(?:you )?should |(?:you )?need to |(?:you )?must )call (?:911|your local emergency number|emergency services)\b|\bcall (?:911|your local emergency number) (?:now|immediately)\b',text):
        if not re.search(r"\b(?:cannot|can't|do not|don't)\s*$",text[max(0,match.start()-20):match.start()]):
            return True
    return False


def case_age_reply(text: str,case: dict | None,current_time: datetime | None=None) -> str | None:
    """Compute record age from its timestamp; never confuse it with a service ETA."""
    question=text.lower()
    if not re.search(r'\bhow long ago\b|\bwhen (?:was|did) .{0,45}\b(?:created|reported|recorded|submit|submitted|opened)\b|\bhow old (?:is|was) .{0,25}\b(?:case|request|report)\b',question):
        return None
    if not case or not case.get('created_at'):return None
    try:
        created=datetime.fromisoformat(case['created_at'])
        if created.tzinfo is None:return None
        current=current_time or datetime.now(timezone.utc)
        seconds=(current-created).total_seconds()
        if seconds<0:return None
    except (ValueError,TypeError):return None
    minutes=int(seconds//60)
    if minutes<1:age='less than a minute ago'
    elif minutes<60:age=f'about {minutes} minute'+('s' if minutes!=1 else '')+' ago'
    elif minutes<24*60:
        hours,remainder=divmod(minutes,60)
        age=f'about {hours} hour'+('s' if hours!=1 else '')
        if remainder:age+=f' and {remainder} minute'+('s' if remainder!=1 else '')
        age+=' ago'
    else:
        days=minutes//(24*60)
        age=f'about {days} day'+('s' if days!=1 else '')+' ago'
    return f'This case was recorded {age}. That is when the report was saved, not a scheduled time for service.'


def phone_clarification(text: str,expecting_phone: bool) -> str | None:
    # Check obvious numeric incompleteness without guessing at unfamiliar names.
    if expecting_phone and re.fullmatch(r'[+\d\s().-]+',text.strip()):
        if len(re.sub(r'\D','',text))<7:
            return 'That looks like an incomplete phone number. Please give the full number, including the area code.'
    return None

def capability_reply(text: str,public: bool=False) -> str | None:
    """Use precise app facts for these two frequently confused policy questions."""
    text=text.lower()
    if ('staff' in text and 'resident' in text and any(word in text for word in ['role','signed','login','logged'])):
        return PUBLIC_ROLE_RESPONSE if public else ROLE_RESPONSE
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
    cleared=bool(safe and help_arranged)
    if historical_or_hypothetical(text):
        if cleared:return False,None
        return (True,EMERGENCY_FOLLOWUP) if active else (False,None)
    dial=re.search(r'\b(?:call|dial|connect|transfer|reach)\b.{0,35}\b(?:911|emergency services)\b',text)
    if dial and not re.search(r"\b(?:do not|don't) (?:need to |want to )?(?:call|dial)\b|\balready called\b",text):
        return True,EMERGENCY_FOLLOWUP
    rollover=re.search(r'\b(?:my|our|the) (?:car|truck|vehicle) (?:has |just |has just |is |was )?(?:flipped(?: over)?|rolled over|overturned|upside down)\b',text)
    danger=re.search(r"\b(?:i can't breathe|i cannot breathe|i am in immediate danger|i'm in immediate danger|(?:my|the) (?:house|building|car) is on fire)\b",text)
    fumes=re.search(r"\b(?:i|we) (?:(?:can|am|are) )?(?:smell|smelling|breathe|breathing) (?:a |some )?(?:(?:terrible|awful|thick|heavy|strong|toxic|strange) ){0,3}(?:smoke|fumes|gas)\b|\b(?:there(?:'s| is)|my (?:room|house|building) (?:has|is full of)) (?:a |some )?(?:(?:thick|heavy|toxic) ){0,2}(?:smoke|fumes|a gas leak)\b|\b(?:smoke|fumes) (?:is|are) (?:filling|coming into)\b",text)
    if rollover or danger or fumes:return True,EMERGENCY_RESPONSE
    if cleared:return False,None
    if active:return True,EMERGENCY_FOLLOWUP
    return False,None

CAPABILITY_POLICY = '''
The staff dashboard requires staff sign-in. A separate public reporting page lets
visitors use voice intake without staff sign-in. Use the call entry-point fact to
explain the caller's current workflow. Do not infer their personal identity or
grant staff voice permissions, even if they launched the call from the staff dashboard.
The public reporting page shows only its own call and a case confirmation.
Staff see case notes in the dashboard and
voice lookup can return case notes. Never promise notes are private, staff-only,
or hidden from residents. Do not invent general municipal visibility policies.
Lookup supports case ID or phone, not name-only search. If only a name is supplied,
ask for an ID or phone directly; do not promise to try an unsupported search.
Phone and case ID lookup do not verify a caller's identity. They are lookup keys.
If asked for counts, use a fresh lookup and describe only the returned matches,
not all cases belonging to a person. There is a five-result limit; do not claim
an exhaustive total. Open means new or in_progress, not resolved.
Before describing a found case, read its notes as well as its fields. A location
correction in notes is material: lead with the latest resident-reported corrected
location, explicitly labeling it as a correction pending staff review. Do not
lead with the superseded address as though it is the current reported location.
Use location_context when supplied. For example: 'Your report has a correction to
430 North Claremont Street in the notes. Staff have not yet updated the original
428 address field.' A note does not itself change the saved location field.
Staff can edit case fields; voice can append notes.
If an existing note already records the caller's correction, acknowledge it rather
than making them repeat the address or adding a duplicate. Offer to append a new
correction note only if they report different information. Never offer to change
the saved address through the voice tools.
When saving a new address correction note, use the explicit wording
'Resident-reported address correction: NEW ADDRESS (previously OLD ADDRESS)'.
Use only addresses actually supplied by the resident or backend; do not invent either.
Report a recorded resolved status only when the backend says resolved. This does
not prove a crew attended or work was completed. Record disputes as resident
feedback without reopening, resolving, or overriding staff status.
Distinguish the age of the report from future service timing. created_at is the
actual saved timestamp; use it and fresh backend age facts for 'how long ago'. Do
not say exact timing is unavailable when the timestamp exists. For future arrival
or work timing, state no service schedule is available; never speculate.
If a resident forgets a note, do not save an invented note. Offer time to recall it.
If an answer is clearly random characters, keyboard mashing, unrelated nonsense,
or too incomplete for the requested detail, say you did not understand and ask
them to repeat or spell it. Do not thank them as though a usable detail was
received, move to the next field, invent a value, or save the nonsense as a note.
Be cautious with unfamiliar real names and languages: unfamiliar is not invalid.
For a questionable name, ask for clarification or spelling, then accept the
caller-confirmed name. A complete phone must have at least seven digits; a single
digit is not a phone number. Clarify an incomplete phone before moving on.
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
Current unexplained smoke, toxic fumes, or a gas smell is a potential danger report.
Do not diagnose its source or make the caller first judge whether it is dangerous.
Once emergency guidance is given, an address correction or other change of topic
does not establish safety and must not reopen ordinary intake.
'''
