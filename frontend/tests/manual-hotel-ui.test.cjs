const assert=require('node:assert/strict');
const fs=require('node:fs');
const test=require('node:test');
const ts=require('typescript');
for(const extension of ['.ts','.tsx'])require.extensions[extension]=(module,filename)=>{
  const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,esModuleInterop:true}});
  module._compile(compiled.outputText,filename);
};
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {ParticipantIdentity}=require('../components/ParticipantIdentity.tsx');
const {ParticipantRow,AllocationGroupCard}=require('../components/ResultsPresentation.tsx');
const {AccessibilityFlagsDialog}=require('../components/AccessibilityFlagsDialog.tsx');
const {addHotelRoom,nextRoomNumber,removeEmptyHotelRoom,withoutEmptyHotelRooms,resetHotelToGenerated}=require('../components/hotelEditing.ts');
const {hotelRoomSummary}=require('../components/hotelSummary.ts');
const render=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
const person={id:'P0',name:'Fictional Hire',attributes:{Gender:'Male',University:'Cairo University'}};
const snapshot=()=>({status:'FEASIBLE',seed:42,activities:[
  {activity_id:'main',activity_name:'Main Groups',groups:[{id:'M0',name:'Group 1',participant_ids:['P0']}]},
  {activity_id:'hotel',activity_name:'Hotel Rooms',groups:[{id:'R1',name:'Room 1 — Single Occupancy',participant_ids:['P0']},{id:'R9',name:'Room 9 — Single Occupancy',participant_ids:['F0']}]},
]});

test('flags default to absent and the selected indicator leaves existing identity markers intact',()=>{
  const props={name:person.name,gender:'Male',category:'public'};
  assert.doesNotMatch(render(ParticipantIdentity,props),/accessibility-indicator|Disability indicator/);
  const marked=render(ParticipantIdentity,{...props,accessibilityFlag:true});
  assert.equal((marked.match(/class="accessibility-indicator"/g)||[]).length,1);
  assert.match(marked,/title="Disability indicator — administrative awareness only"/);
  assert.match(marked,/aria-label="Disability indicator — administrative awareness only"/);
  assert.match(marked,/university-public/);assert.match(marked,/Gender: Male/);
});
test('participant rows never apply flags to staff identities',()=>{
  for(const role of ['Faculty','Support Lead','Analyst Support']){
    assert.doesNotMatch(render(ParticipantRow,{index:1,name:'Fictional Staff',role,chemistryEnabled:false,accessibilityFlag:true}),/accessibility-indicator/);
  }
  assert.match(render(ParticipantRow,{index:1,name:person.name,person,chemistryEnabled:false,accessibilityFlag:true}),/accessibility-indicator/);
});
test('flags dialog has a searchable cohort, no default flags, and explicit Save/Cancel controls',()=>{
  const props={people:[person],savedIds:[],save:()=>{},cancel:()=>{}};
  const plain=render(AccessibilityFlagsDialog,props);
  assert.match(plain,/Search new hires/);assert.match(plain,/Cairo University/);
  assert.match(plain,/0 selected/);assert.match(plain,/Save Flags/);assert.match(plain,/>Cancel</);
  assert.doesNotMatch(plain,/<input[^>]+checked/);
  assert.match(render(AccessibilityFlagsDialog,{...props,savedIds:['P0']}),/1 selected/);
  assert.equal(person.id,'P0');assert.ok(!('accessibility' in person.attributes));
});
test('room numbering survives reordering, deletion and the previous high-water number',()=>{
  const original=snapshot();assert.equal(nextRoomNumber(original),10);
  original.activities[1].groups.reverse();assert.equal(nextRoomNumber(original),10);
  assert.equal(nextRoomNumber(original,14),15);
});
test('multiple added rooms are unique, append after existing rooms and never mutate other activities',()=>{
  const original=snapshot(),before=structuredClone(original);
  const first=addHotelRoom(original,'hotel-manual-one',10);
  const second=addHotelRoom(first,'hotel-manual-two',11);
  assert.deepEqual(original,before);
  assert.deepEqual(second.activities[0],before.activities[0]);
  assert.deepEqual(second.activities[1].groups.map(g=>g.name),['Room 1 — Single Occupancy','Room 9 — Single Occupancy','Room 10','Room 11']);
  assert.equal(new Set(second.activities[1].groups.map(g=>g.id)).size,4);
  assert.throws(()=>addHotelRoom(second,'hotel-manual-one',12),/unique/);
});
test('only unused manual rooms are removable and existing numbering stays stable',()=>{
  const original=snapshot();const extra=addHotelRoom(original,'hotel-manual-one',10);
  assert.deepEqual(removeEmptyHotelRoom(extra,'hotel-manual-one'),original);
  assert.throws(()=>removeEmptyHotelRoom(extra,'R1'),/Only an empty/);
  extra.activities[1].groups.at(-1).participant_ids=['P1'];
  assert.throws(()=>removeEmptyHotelRoom(extra,'hotel-manual-one'),/Only an empty/);
});
test('empty draft rooms do not count as bookings and Save discards only empty rooms',()=>{
  const original=snapshot(),extra=addHotelRoom(original,'hotel-manual-one',10);
  const summary=hotelRoomSummary(extra.activities[1].groups,{P0:person},{},[{id:'F0',name:'Fictional Faculty',offering:'Cyber'}]);
  assert.equal(summary.total_rooms,2);assert.equal(summary.new_hire_single,1);assert.equal(summary.faculty_single,1);
  assert.deepEqual(withoutEmptyHotelRooms(extra),original);
  extra.activities[1].groups.at(-1).participant_ids=['P1'];
  assert.equal(withoutEmptyHotelRooms(extra).activities[1].groups.length,3);
});
test('hotel Reset to Generated preserves manual assignments in unrelated activities',()=>{
  const generated=snapshot(),draft=addHotelRoom(generated,'hotel-manual-one',10);
  draft.activities[0]={...draft.activities[0],groups:[{id:'manual-main',name:'Manually saved group',participant_ids:['P0']}]};
  const reset=resetHotelToGenerated(draft,generated);
  assert.deepEqual(reset.activities[0],draft.activities[0]);
  assert.deepEqual(reset.activities[1],generated.activities[1]);
  assert.equal(draft.activities[1].groups.length,3);
});
test('empty cards use the existing room-card structure and explicit empty occupancy',()=>{
  const markup=render(AllocationGroupCard,{title:'Room 12',count:0,index:12,activityId:'hotel',room:{className:'hotel-room-neutral',warning:''},children:'Drag a participant here'});
  assert.match(markup,/allocation-group-card hotel-room hotel-room-neutral/);
  assert.match(markup,/Empty room · 0 occupants/);assert.match(markup,/Drag a participant here/);
});
