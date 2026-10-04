from backend.locations import location_context,corrected_location_reply


def test_existing_correction_is_reported_without_mutating_saved_address():
    case={'location':'428 North Claremont Street','notes':[{'text':'Reported updated address: 430 North Claremont Street (corrected from 428 North Claremont Street).'}]}
    context=location_context(case)
    assert context['reported_correction']=='430 North Claremont Street'
    assert context['saved_location']==case['location']=='428 North Claremont Street'
    reply=corrected_location_reply({**case,'id':'EG-119B5C','status':'new'})
    assert reply.index('430')<reply.index('428')
    case['location']='432 North Claremont Street'
    assert location_context(case)['reported_correction'] is None


def test_latest_explicit_correction_wins_without_treating_any_address_as_correction():
    case={'location':'50 East Avenue','notes':[{'text':'Resident correction: The address is fifty-one East Avenue, not 50 East Avenue.'},
           {'text':'Resident-reported address correction: 52 East Avenue (previously 50 East Avenue)'},
           {'text':'A crew visited 99 Other Street.'}]}
    assert location_context(case)['reported_correction']=='52 East Avenue'
    assert location_context({'location':'50 East Avenue','notes':case['notes'][-1:]})['reported_correction'] is None


def test_spoken_previous_address_matches_numeric_saved_field():
    case={'location':'50 East Avenue','notes':[{'text':'Resident correction: The address is fifty-one East Avenue, not fifty East Avenue.'}]}
    assert location_context(case)['reported_correction']=='fifty-one East Avenue'
