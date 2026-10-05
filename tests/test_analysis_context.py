import json
from backend.analysis import analysis_input


def test_lookup_does_not_attribute_an_earlier_calls_note_to_this_call():
    call={'id':'lookup-call','started_at':'2026-10-04T23:00:00Z','transcript':[{'role':'user','text':'I thought you left a correction note.'}]}
    earlier_note={'text':'Reported updated address: 430 (previously 428)','call_id':'earlier-call'}
    case={'notes':[earlier_note], 'audit':[{'call_id':'earlier-call','fields':{'notes':'changed'}}]}
    context=json.loads(analysis_input(call,case).split('Backend confirmed context: ')[1])
    assert context['pre_existing_notes']==[earlier_note]
    assert context['notes_added_this_call']==context['confirmed_actions_this_call']==[]
    current_note={'text':'New feedback','call_id':call['id']}
    case['notes'].append(current_note)
    case['audit'].append({'call_id':call['id'],'fields':{'notes':'changed'}})
    context=json.loads(analysis_input(call,case).split('Backend confirmed context: ')[1])
    assert context['notes_added_this_call']==[current_note]
    assert len(context['confirmed_actions_this_call'])==1


def test_analysis_includes_both_created_cases():
    call={'id':'multi-call','started_at':'2026-10-04T23:00:00Z','transcript':[]}
    records=[{'id':'EG-111111','audit':[{'call_id':'multi-call','fields':{'description':'First report'}}]},
             {'id':'EG-222222','audit':[{'call_id':'multi-call','fields':{'description':'Second report'}}]}]
    context=json.loads(analysis_input(call,records[-1],cases=records).split('Backend confirmed context: ')[1])
    assert len(context['confirmed_actions_this_call'])==2
    assert context['cases']==records
