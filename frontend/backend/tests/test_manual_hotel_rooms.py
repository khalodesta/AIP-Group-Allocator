"""Manual private rooms are draft edits, never new optimizer inputs."""
import copy
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from app.main import app
from app.models import Configuration
from test_exports_improvements import manifest_fixture, pdf_text

client=TestClient(app)


@pytest.fixture
def payload():
    people,support,faculty,allocation=manifest_fixture()
    for key,title in [('quiz','Quiz Night'),('team','Team Building')]:
        activity=allocation.activities[0].model_copy(deep=True)
        activity.activity_id=key;activity.activity_name=title
        for group in activity.groups: group.id=f'{key}-{group.id}'
        allocation.activities.insert(-1,activity)
    return dict(participants=[p.model_dump() for p in people],support_members=[s.model_dump() for s in support],
                faculty_members=[f.model_dump() for f in faculty],allocation=allocation.model_dump(),
                configuration=Configuration(activities=[]).model_dump())


def hotel(payload):
    return next(a for a in payload['allocation']['activities'] if a['activity_id']=='hotel')


def add(payload, number=11):
    room=dict(id=f'hotel-manual-{number}',name=f'Room {number}',participant_ids=[])
    hotel(payload)['groups'].append(room)
    return room


def move(payload, person, room, **kwargs):
    return client.post('/api/allocations/edit',json={**payload,'activity_id':'hotel',
        'participant_id':person,'target_group_id':room['id'],**kwargs})


def saved(payload):
    result=copy.deepcopy(payload)
    hotel(result)['groups']=[room for room in hotel(result)['groups'] if room['participant_ids']]
    return result


@pytest.mark.parametrize('odd',[False,True])
def test_split_shared_room_keeps_both_singles_and_all_other_activities(payload,odd):
    if odd:
        payload['participants']=[p for p in payload['participants'] if p['id']!='P5']
        for activity in payload['allocation']['activities']:
            for group in activity['groups']: group['participant_ids']=[pid for pid in group['participant_ids'] if pid!='P5']
    before=copy.deepcopy(payload)
    destination=add(payload);unused=add(payload,12)
    response=move(payload,'P0',destination)
    assert response.status_code==200,response.text
    result=response.json()
    assert not result.get('requires_confirmation') and not result['conflicts']
    payload['allocation']=result['allocation']
    rooms={r['id']:r for r in hotel(payload)['groups']}
    assert rooms['R0']['participant_ids']==['P1']
    assert rooms[destination['id']]['participant_ids']==['P0']
    assert rooms[unused['id']]['participant_ids']==[]
    assert hotel(payload)['room_summary']['total_rooms']==len(hotel(before)['groups'])+1
    assert hotel(payload)['warnings']==[]
    for activity in before['allocation']['activities']:
        if activity['activity_id']!='hotel':
            assert activity==next(a for a in payload['allocation']['activities'] if a['activity_id']==activity['activity_id'])
    # Empty destinations exist only during editing; Save removes them first.
    assert not client.post('/api/allocations/validate',json=payload).json()['valid']
    final=saved(payload)
    assert client.post('/api/allocations/validate',json=final).json()['valid']
    ids=[pid for r in hotel(final)['groups'] for pid in r['participant_ids']]
    assert len(ids)==len(set(ids))==len(payload['participants'])+7
    assert sum(v for k,v in hotel(final)['room_summary'].items() if k!='total_rooms')==hotel(final)['room_summary']['total_rooms']


def test_saved_private_room_is_identical_in_pdf_excel_and_manifest(payload):
    destination=add(payload);add(payload,12)
    response=move(payload,'P0',destination)
    payload['allocation']=response.json()['allocation']
    final=saved(payload)
    pdf=client.post('/api/export/hotel-pdf',json=final)
    assert pdf.status_code==200,pdf.text
    text=' '.join(pdf_text(pdf.content).split())
    assert 'Room 11' in text and 'Room 12' not in text
    assert 'Single Occupancy' in text and 'Total rooms required: 11' in text
    assert 'accommodation review' not in text
    assert text.count('Fictional Hire 0')==text.count('Fictional Hire 1')==1
    excel=client.post('/api/export/editable',json=final)
    assert excel.status_code==200
    book=load_workbook(io.BytesIO(excel.content))
    rows=list(book['Hotel Rooms'].values)
    new=next(r for r in rows[1:] if r[0].startswith('Room 11'))
    original=next(r for r in rows[1:] if r[0].startswith('Room 1 '))
    assert new[1]=='Fictional Hire 0' and new[2]=='New Hire' and new[3] is None and new[5]==1
    assert original[1]=='Fictional Hire 1' and original[5]==1
    assert len(rows)-1==11
    names=[r[index] for r in rows[1:] for index in (1,3) if r[index]]
    assert len(names)==len(set(names))==13
    totals=dict(list(book['Hotel Summary'].values)[1:])
    assert totals['Total rooms required']==11
    public=client.post('/api/export/pdf',json=final)
    assert public.status_code==200 and 'Room 11' not in pdf_text(public.content)
    for content in (text,pdf_text(public.content),' '.join(str(c.value) for ws in book for row in ws for c in row)):
        assert 'Disability indicator' not in content and 'Accessibility Flags' not in content


def test_move_to_one_person_room_and_swap_do_not_regenerate(payload):
    room=add(payload)
    payload['allocation']=move(payload,'P0',room).json()['allocation']
    # Returning to the original roommate is a move; the now empty manual room stays a draft.
    original=next(r for r in hotel(payload)['groups'] if r['id']=='R0')
    response=move(payload,'P0',original)
    assert response.status_code==200
    payload['allocation']=response.json()['allocation']
    assert next(r for r in hotel(payload)['groups'] if r['id']==room['id'])['participant_ids']==[]
    assert set(next(r for r in hotel(payload)['groups'] if r['id']=='R0')['participant_ids'])=={'P0','P1'}
    payload['allocation']=move(payload,'P0',room).json()['allocation']
    response=move(payload,'P1',room,swap_with_id='P0')
    assert response.status_code==200
    rooms={r['id']:r['participant_ids'] for r in response.json()['allocation']['activities'][-1]['groups']}
    assert rooms[room['id']]==['P1'] and rooms['R0']==['P0']


@pytest.mark.parametrize('person',['S0','F0'])
def test_leads_and_faculty_can_move_to_an_empty_room_but_must_stay_alone(payload,person):
    destination=add(payload)
    response=move(payload,person,destination)
    assert response.status_code==200
    payload['allocation']=response.json()['allocation']
    assert client.post('/api/allocations/validate',json=saved(payload)).json()['valid']
    response=move(payload,'P0',destination)
    assert response.status_code==422 and 'single-occupancy' in response.text


def test_analyst_support_pairing_cannot_be_bypassed_by_a_manual_room(payload):
    destination=add(payload)
    payload['allocation']=move(payload,'S2',destination).json()['allocation']
    response=move(payload,'S3',destination)
    assert response.status_code==422 and 'Analyst Support can share only' in response.text
    response=move(payload,'P0',destination)
    assert response.status_code==200 and not response.json().get('requires_confirmation')


def test_capacity_two_is_hard_even_when_policy_overrides_are_enabled(payload):
    destination=add(payload)
    payload['allocation']=move(payload,'P0',destination).json()['allocation']
    payload['allocation']=move(payload,'P1',destination).json()['allocation']
    payload['configuration']['allow_accommodation_policy_overrides']=True
    response=move(payload,'P2',destination,allow_override=True)
    assert response.status_code==422 and 'maximum capacity of two' in response.text


def test_gender_and_main_group_approval_rules_still_apply_to_manual_rooms(payload):
    destination=add(payload)
    payload['allocation']=move(payload,'P0',destination).json()['allocation']
    blocked=move(payload,'P3',destination)
    assert blocked.json()['requires_confirmation']
    assert any(c['rule']=='mixed_gender_room' and not c['overridable'] for c in blocked.json()['conflicts'])
    assert move(payload,'P3',destination,allow_override=True).status_code==422
    payload['configuration']['allow_accommodation_policy_overrides']=True
    assert move(payload,'P3',destination,allow_override=True).status_code==200
    # Same-gender new hires sharing a Main Group still require the existing warning approval.
    proposal=move(payload,'P2',destination)
    assert proposal.json()['requires_confirmation']
    assert any(c['rule']=='roommates_same_main' for c in proposal.json()['conflicts'])
    assert move(payload,'P2',destination,allow_override=True).status_code==200


@pytest.mark.parametrize('mutation',['duplicate','missing','unknown','duplicate_room_id','empty','overcapacity'])
def test_invalid_saved_manifests_cannot_be_exported(payload,mutation):
    rooms=hotel(payload)['groups']
    if mutation=='duplicate': rooms[1]['participant_ids']=['P0','P2']
    elif mutation=='missing': rooms[0]['participant_ids']=['P0']
    elif mutation=='unknown': rooms[0]['participant_ids']=['P0','not-a-person']
    elif mutation=='duplicate_room_id': rooms[1]['id']=rooms[0]['id']
    elif mutation=='empty': add(payload)
    else:
        rooms[0]['participant_ids'].append('P2');rooms[1]['participant_ids'].remove('P2')
        payload['configuration']['allow_accommodation_policy_overrides']=True
    for endpoint in ('/api/export/hotel-pdf','/api/export/editable'):
        assert client.post(endpoint,json=payload).status_code==422


def test_long_names_and_multiple_private_rooms_remain_in_saved_exports(payload):
    payload['participants'][0]['name']='Fictional Hire With An Exceptionally Long Full Name For Accommodation Review'
    for person,number in [('P0',11),('P4',12)]:
        room=add(payload,number)
        response=move(payload,person,room)
        assert response.status_code==200
        payload['allocation']=response.json()['allocation']
    final=saved(payload)
    assert client.post('/api/allocations/validate',json=final).json()['valid']
    assert hotel(final)['room_summary']['single_new_hire_rooms']==5
    response=client.post('/api/export/hotel-pdf',json=final)
    assert response.status_code==200
    text=' '.join(pdf_text(response.content).split())
    assert payload['participants'][0]['name'] in text
    assert 'Total rooms required: 12' in text
