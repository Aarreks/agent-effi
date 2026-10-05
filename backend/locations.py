"""Present explicit address corrections in notes without silently editing case fields."""
import re
from datetime import datetime


def address_key(value: str) -> str:
    """Match common spoken street numbers without altering display wording."""
    value=value.lower().replace('-',' ')
    units={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,
           'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19}
    tens={'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
    words=value.split()
    if words and words[0] in units|tens:
        number=(units|tens)[words[0]];used=1
        if words[0] in tens and len(words)>1 and words[1] in units and units[words[1]]<10:
            number+=units[words[1]];used=2
        value=str(number)+' '+' '.join(words[used:])
    return re.sub(r'[^\w]','',value)


def location_context(case: dict) -> dict:
    stored=case.get('location','')
    result={'saved_location':stored,'reported_correction':None,'correction_note':None}
    # Prefer the newest explicit correction, not an arbitrary address mentioned in
    # a general note. Keep the resident's exact wording rather than inventing one.
    patterns=[
        r'(?:reported updated address|resident-reported address correction|address correction):\s*(.+?)(?:\s*\((?:corrected from|previously)\s+(.+?)\)|$)',
        r'(?:resident correction:\s*)?(?:the )?address is\s+(.+?),\s*not\s+(.+?)[.!]?$',
    ]
    normalize=address_key
    for note in reversed(case.get('notes',[])):
        reviewed=case.get('location_reviewed_at')
        if reviewed:
            try:
                if not note.get('at') or datetime.fromisoformat(note['at'])<=datetime.fromisoformat(reviewed):continue
            except (ValueError,TypeError):continue
        text=note.get('text','').strip()
        for pattern in patterns:
            match=re.search(pattern,text,re.I)
            if not match:continue
            reported=match.group(1).strip().rstrip('.')
            previous=match.group(2)
            if not reported or len(reported)>300:continue
            if normalize(reported)==normalize(stored):return result
            # A later staff address change supersedes a correction to an older
            # original field. Do not resurrect that obsolete correction.
            if previous and normalize(previous.strip().rstrip('.'))!=normalize(stored):continue
            result.update(reported_correction=reported,correction_note=text)
            return result
    return result


def corrected_location_reply(case: dict) -> str | None:
    context=location_context(case)
    reported=context['reported_correction']
    if not reported:return None
    statuses={'new':'awaiting staff review','in_progress':'in progress','resolved':'resolved'}
    identity=case.get('id','');status=statuses.get(case.get('status'))
    if not re.fullmatch(r'EG-[A-F0-9]{6}',identity) or not status:return None
    return (f'The reported location is {reported}, according to the recorded address correction note. '
            f'The original address field still shows {context["saved_location"]}, pending a staff update. '
            f'Case {identity} is {status}.')
