"""Verify the actual files downloaded by accessibility-hotel-browser.cjs."""
import argparse
import json
from pathlib import Path
import re

from openpyxl import load_workbook
from pypdf import PdfReader

parser=argparse.ArgumentParser()
parser.add_argument('artifacts',type=Path)
args=parser.parse_args()
payload=json.loads((args.artifacts/'saved-manifest.json').read_text())
hotel=next(a for a in payload['allocation']['activities'] if a['activity_id']=='hotel')
names={p['id']:p['name'] for key in ('participants','support_members','faculty_members') for p in payload[key]}
roles={p['id']:'New Hire' for p in payload['participants']}
roles.update({s['id']:s['category'] for s in payload['support_members']})
roles.update({f['id']:'Faculty' for f in payload['faculty_members']})
book=load_workbook(args.artifacts/'saved-hotel.xlsx')
rows=list(book['Hotel Rooms'].values)[1:]
assert len(rows)==len(hotel['groups'])
for actual,expected in zip(rows,hotel['groups']):
    ids=expected['participant_ids']
    assert 1<=len(ids)<=2
    assert actual[0]==expected['name']
    assert actual[1]==names[ids[0]] and actual[2]==roles[ids[0]]
    assert actual[3]==(names[ids[1]] if len(ids)>1 else None)
    assert actual[4]==(roles[ids[1]] if len(ids)>1 else None)
    assert actual[5]==len(ids)
total=dict(list(book['Hotel Summary'].values)[1:])['Total rooms required']
assert total==len(rows)
private=' '.join(' '.join(page.extract_text() or '' for page in PdfReader(args.artifacts/'saved-private-hotel.pdf').pages).split())
public=' '.join(page.extract_text() or '' for page in PdfReader(args.artifacts/'saved-public.pdf').pages)
assert f'Total rooms required: {len(rows)}' in private
chunks=re.split(r'(?=\bRoom \d+\b)',private)[1:]
assert len(chunks)==len(hotel['groups'])
for room,chunk in zip(hotel['groups'],chunks):
    assert chunk.startswith(room['name'])
    for pid in room['participant_ids']: assert names[pid] in chunk
    if len(room['participant_ids'])==1: assert 'Single' in chunk
for name in names.values(): assert private.count(name)==1,name
assert 'Room ' not in public and 'PRIVATE HOTEL' not in public
for content in [private,public,' '.join(str(c.value) for sheet in book for row in sheet for c in row)]:
    assert 'Disability indicator' not in content and 'Accessibility Flags' not in content
summary={'passed':True,'rooms':len(rows),'occupants':len(names),'same_manifest_in_ui_pdf_excel':True,'empty_rooms_exported':False,'flags_exported':False}
(args.artifacts/'export-verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
