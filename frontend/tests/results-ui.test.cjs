const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
// Compile the real components for dependency-free React SSR behavior tests.
for (const extension of ['.ts', '.tsx']) require.extensions[extension] = (module, filename) => {
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,esModuleInterop:true}});
  module._compile(compiled.outputText, filename);
};
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {ParticipantIdentity,ResultsLegend,genderRowClass,hotelRoomAppearance} = require('../components/ParticipantIdentity.tsx');
const {UniversityReview} = require('../components/UniversityReview.tsx');
const {ReflectionResultsSummary} = require('../components/ReflectionResultsSummary.tsx');
const {eligiblePrayerParticipants,prunePrayerSelection,latestAppointmentEnd} = require('../components/reflectionUi.ts');
const {UNIVERSITY_CATEGORIES,canonicalCategory,classifyUniversity,classifiedParticipants,mergedUniversityDirectory,parseCustomDirectory,migrateCustomDirectory} = require('../components/universityClassification.ts');
const {hotelRoomSummary} = require('../components/hotelSummary.ts');
const {ParticipantRow,AllocationGroupCard,HotelResultsSummary,FacultyScheduleHeader} = require('../components/ResultsPresentation.tsx');
const directory = JSON.parse(fs.readFileSync(path.join(__dirname,'../backend/data/university_directory.json'),'utf8')).universities;
const person=(id,university='Cairo University',gender='Male')=>({id,name:`Fictional ${id}`,attributes:{University:university,Gender:gender}});
const render=(Component,props={})=>renderToStaticMarkup(React.createElement(Component,props));
const custom=(id,name,category,aliases=[])=>({id,name,aliases,category});

test('only Public and Private are grouping categories; unsupported legal categories need review',()=>{
  assert.deepEqual(UNIVERSITY_CATEGORIES,{public:'Public',private:'Private'});
  assert.equal(canonicalCategory('public_technological'),'public');
  assert.equal(canonicalCategory('private_technological'),'private');
  for(const category of ['national','national_ahlia','international','foreign_branch','special_nature','other','toString',null])assert.equal(canonicalCategory(category),undefined);
  assert.equal(classifyUniversity('CU',directory,[]),'public');
  assert.equal(classifyUniversity('GUC',directory,[]),'private');
  assert.equal(classifyUniversity('AUC',directory,[]),'private');
  assert.equal(classifyUniversity('Helwan National University',directory,[]),undefined);
  assert.equal(classifyUniversity('UPEI Cairo',directory,[]),undefined);
  assert.equal(classifyUniversity('Fictional Unknown Academy',directory,[]),undefined);
});
test('Capital-Helwan aliases share identity while Helwan National stays separate and unconfirmed',()=>{
  const classified=classifiedParticipants(['Helwan University','Capital University','Capital-Helwan University','جامعة حلوان','جامعة العاصمة','Helwan National University'].map((name,index)=>person(String(index),name)),directory,[]);
  assert.deepEqual(classified.slice(0,5).map(p=>p.attributes.University),Array(5).fill('Capital-Helwan University'));
  assert.equal(classified[5].attributes.University,'Helwan National University');
  assert.equal(classified[5].attributes['University Category'],null);
});
test('custom confirmation applies to aliases and overrides a known grouping category',()=>{
  const entries=parseCustomDirectory({universities:[custom('custom:fictional academy','Fictional Academy','private',['FA','Fictional-Academy']),custom('eg-cairo-university','Cairo University','private',['CU'])]});
  assert.equal(classifyUniversity(' fA ',directory,entries),'private');
  assert.equal(classifyUniversity('Fictional-Academy',directory,entries),'private');
  assert.equal(classifyUniversity('Cairo University',directory,entries),'private');
  const merged=mergedUniversityDirectory(directory,entries);
  assert.equal(merged.filter(u=>u.id==='eg-cairo-university').length,1);
  assert.equal(merged.find(u=>u.id==='custom:fictional academy').diversity_category,'private');
  assert.equal(merged.find(u=>u.id==='eg-cairo-university').category,'public'); // legal metadata stays intact
});
test('directory import rejects unsupported category mappings with explicit review instructions',()=>{
  for(const category of ['national','international','other','toString'])assert.throws(()=>parseCustomDirectory([custom('one','Fictional Academy',category)]),/Public or Private classification required.*Review/);
  assert.throws(()=>parseCustomDirectory([custom('one','First','public',['FA']),custom('two','Second','private',['fa'])]),/more than one/);
  assert.throws(()=>parseCustomDirectory([custom('same','First','public'),custom('same','Second','private')]),/duplicate/);
});
test('legacy storage preserves binary mappings and retains unsupported identity aliases for review only',()=>{
  const migrated=migrateCustomDirectory({universities:[custom('one','Valid Academy','public'),custom('two','Fictional Legacy Academy','national',['FLA']),custom('three','Valid Private Academy','private')]});
  assert.deepEqual(migrated.universities.map(item=>item.category),['public','private']);
  assert.deepEqual(migrated.pending,[{id:'two',name:'Fictional Legacy Academy',aliases:['FLA']}]);
  assert.ok(!('category' in migrated.pending[0]));
  const merged=mergedUniversityDirectory(directory,migrated.universities,migrated.pending);
  assert.equal(classifyUniversity('FLA',merged,migrated.universities),undefined);
  const markup=render(UniversityReview,{people:[person('one','FLA'),person('two','Fictional Legacy Academy')],directory:merged,custom:migrated.universities,pending:migrated.pending,confirm:()=>true});
  assert.match(markup,/Confirm 1 unique university/);
  const restored=migrateCustomDirectory({universities:migrated.universities,pending_review:migrated.pending});
  assert.deepEqual(restored,migrated);
});
test('classification review asks once per institution with only two selectable categories',()=>{
  const markup=render(UniversityReview,{people:[person('1','Fictional Academy'),person('2','fictional-academy')],directory,custom:[],confirm:()=>true});
  assert.match(markup,/University classification required/);
  assert.match(markup,/Confirm 1 unique university/);
  assert.equal((markup.match(/Category for Fictional Academy/g)||[]).length,1);
  assert.match(markup,/<option value="" selected="">Choose category<\/option>/);
  assert.match(markup,/<option value="public">Public<\/option>/);
  assert.match(markup,/<option value="private">Private<\/option>/);
  assert.doesNotMatch(markup,/<option value="(?:national|international|other)"/);
});
test('one confirmed imported cohort mapping applies to every same-university row and alias',()=>{
  const first=person('one','Fictional-Academy');first.attributes['University Category']='private';
  const second=person('two','fictional academy');
  assert.deepEqual(classifiedParticipants([first,second],directory,[]).map(p=>p.attributes['University Category']),['private','private']);
  const markup=render(UniversityReview,{people:[first,second],directory,custom:[],confirm:()=>true});
  assert.doesNotMatch(markup,/classification required/);
});
test('conflicting imported cohort categories remain unresolved until an authoritative correction',()=>{
  const first=person('one','Fictional-Academy');first.attributes['University Category']='private';
  const second=person('two','fictional academy');second.attributes['University Category']='public';
  assert.deepEqual(classifiedParticipants([first,second],directory,[]).map(p=>p.attributes['University Category']),[null,null]);
  assert.match(render(UniversityReview,{people:[first,second],directory,custom:[],confirm:()=>true}),/Confirm 1 unique university/);
  const correction=[custom('custom:fictional academy','Fictional Academy','private')];
  assert.deepEqual(classifiedParticipants([first,second],directory,correction).map(p=>p.attributes['University Category']),['private','private']);
});
test('legacy nonbinary imported category never becomes an automatic private assignment',()=>{
  const imported=person('one','Fictional Legacy University');imported.attributes['University Category']='national';
  assert.equal(classifiedParticipants([imported],directory,[])[0].attributes['University Category'],null);
  assert.match(render(UniversityReview,{people:[imported],directory,custom:[],confirm:()=>true}),/classification required/);
});
test('male-only prayer eligibility uses recorded gender and pruning removes stale or ineligible selections',()=>{
  const people=[person('male'),person('female','Cairo University','Female'),person('unknown','Cairo University','')];
  assert.deepEqual(eligiblePrayerParticipants(people).map(p=>p.id),['male']);
  assert.deepEqual(prunePrayerSelection(['male','female','missing','male'],people),['male']);
  people[0].attributes.Gender='Female';
  assert.deepEqual(prunePrayerSelection(['male'],people),[]);
});
test('gender styling belongs to full rows while names have separate accessible binary markers',()=>{
  assert.equal(genderRowClass('Male'),'result-gender-male');assert.equal(genderRowClass('Female'),'result-gender-female');
  assert.equal(genderRowClass(undefined),'result-gender-neutral');
  for(const gender of ['Male','Female'])for(const category of ['public','private']){
    const markup=render(ParticipantIdentity,{name:'Fictional Person',gender,category});
    assert.match(markup,new RegExp(`university-${category}`));
    assert.match(markup,new RegExp(`Gender: ${gender}`));
    assert.match(markup,/aria-label="University category:/);
    assert.doesNotMatch(markup,/person-gender|\(Male,|\(Female,/);
  }
  assert.doesNotMatch(render(ParticipantIdentity,{name:'Fictional Person',category:'national'}),/university-marker/);
});
test('support retains recorded gender and role without invented university; faculty attributes stay unknown',()=>{
  const support=render(ParticipantIdentity,{name:'Fictional Helper',gender:'Female',role:'Analyst Support'});
  assert.match(support,/Gender: Female/);assert.match(support,/Analyst Support/);assert.doesNotMatch(support,/university-marker/);
  const faculty=render(ParticipantIdentity,{name:'Fictional Faculty',role:'Faculty'});
  assert.doesNotMatch(faculty,/Gender:|University category:/);
});
test('legend explains full-row gender colors and exactly two category markers',()=>{
  const markup=render(ResultsLegend);
  for(const label of ['Results color legend','Male rows','Female rows','Public','Private'])assert.ok(markup.includes(label),label);
  assert.doesNotMatch(markup,/National|Ahleya|International|Foreign Branch|Unclassified|Other/);
});
test('hotel appearance uses one whole-room gender and neutral warnings for mixed or unknown occupants',()=>{
  const people={m:person('m'),f:person('f','Cairo University','Female')};
  const support={a:{id:'a',name:'Fictional Analyst',gender:'Male',category:'Analyst Support'}};
  assert.deepEqual(hotelRoomAppearance(['m','a'],people,support),{className:'hotel-room-male',warning:''});
  assert.deepEqual(hotelRoomAppearance(['f'],people,support),{className:'hotel-room-female',warning:''});
  assert.equal(hotelRoomAppearance(['m','f'],people,support).className,'hotel-room-neutral');
  assert.match(hotelRoomAppearance(['m','f'],people,support).warning,/Mixed-gender/);
  assert.equal(hotelRoomAppearance(['faculty'],people,support).className,'hotel-room-neutral');
  assert.match(hotelRoomAppearance(['faculty'],people,support).warning,/not recorded/);
});
test('My Reflections summary has only Participants and actual Completion Time including idle gaps',()=>{
  const sessions=[{participant_id:'1',faculty_id:'one',start_time:'11:15 AM',end_time:'11:35 AM'},
    {participant_id:'2',faculty_id:'two',start_time:'1:00 PM',end_time:'1:20 PM'},
    {participant_id:'3',faculty_id:'three',start_time:'14:00',end_time:'14:20'}];
  const activity={activity_id:'reflection',activity_name:'My Reflections',groups:[],sessions};
  const markup=render(ReflectionResultsSummary,{activity});
  assert.equal((markup.match(/<p class="text-xs/g)||[]).length,2);
  assert.match(markup,/Participants/);assert.match(markup,/Completion Time/);assert.match(markup,/>3<\/p>/);assert.match(markup,/>14:20<\/p>/);
  assert.equal(latestAppointmentEnd(sessions),'14:20');
  assert.doesNotMatch(markup,/Accommodation|Before prayer|After prayer|Offering match|Faculty workloads/);
});
test('hotel summary counts actual unique rooms and all supported occupancy types',()=>{
  const people=Object.fromEntries(['p1','p2','p3','p4'].map(id=>[id,person(id)]));
  const support={a1:{id:'a1',name:'Fictional Analyst One',category:'Analyst Support'},a2:{id:'a2',name:'Fictional Analyst Two',category:'Analyst Support'},l1:{id:'l1',name:'Fictional Lead',category:'Support Lead'}};
  const faculty=[{id:'f1',name:'Fictional Faculty'}];
  const groups=[['p1','p2'],['p3','a1'],['p4'],['l1'],['a2'],['f1']].map((ids,index)=>({id:`room-${index}`,name:`Room ${index+1}`,participant_ids:ids}));
  const summary=hotelRoomSummary(groups,people,support,faculty);
  assert.deepEqual(summary,{total_rooms:6,new_hire_shared:1,new_hire_analyst_shared:1,new_hire_single:1,support_lead_single:1,analyst_support_single:1,faculty_single:1});
  assert.equal(Object.entries(summary).filter(([key])=>key!=='total_rooms').reduce((total,[,count])=>total+count,0),summary.total_rooms);
});


test('confirming a migrated mapping retains its editable alias and resolves the entire cohort',()=>{
  const migrated=migrateCustomDirectory({universities:[custom('custom:fictional saved academy','Fictional Saved Academy','national',['FSA'])]});
  const people=[person('one','Fictional Saved Academy'),person('two','FSA')];
  const merged=mergedUniversityDirectory(directory,migrated.universities,migrated.pending);
  const markup=render(UniversityReview,{people,directory:merged,custom:migrated.universities,pending:migrated.pending,confirm:()=>true});
  const aliasEditor=markup.match(/aria-label="Aliases for Fictional Saved Academy"[^>]*value="([^"]*)"/);
  assert.ok(aliasEditor,'The migrated identity has an editable aliases field.');
  assert.equal(aliasEditor[1],'FSA');
  const confirmed=parseCustomDirectory([{...migrated.pending[0],aliases:aliasEditor[1].split(','),category:'public'}]);
  assert.deepEqual(classifiedParticipants(people,directory,confirmed).map(p=>p.attributes['University Category']),['public','public']);
  assert.doesNotMatch(render(UniversityReview,{people,directory:mergedUniversityDirectory(directory,confirmed),custom:confirmed,confirm:()=>true}),/classification required/);
  // A deliberate correction may still remove the alias; pending metadata must not restore it.
  const corrected=parseCustomDirectory([{...confirmed[0],aliases:[]}]);
  assert.equal(classifyUniversity('FSA',directory,corrected),undefined);
});

test('redesigned participant records preserve full names, long universities, offerings, and optional Chemistry',()=>{
  const participant=person('long','Arab Academy for Science, Technology and Maritime Transport');
  participant.attributes['L3 Offering']='Engineering';
  participant.attributes['Primary Chemistry']='Pioneer';
  participant.attributes['Secondary Chemistry']='Guardian';
  const before=JSON.stringify(participant);
  const props={index:1,name:participant.name,gender:'Male',category:'public',person:participant,offering:'Engineering',chemistryEnabled:true,selected:true};
  const markup=render(ParticipantRow,props);
  for(const value of [participant.name,participant.attributes.University,'Engineering','Pioneer','Guardian','Selected for switching'])assert.ok(markup.includes(value),value);
  assert.doesNotMatch(markup,/truncate|line-clamp/);
  const withoutChemistry=render(ParticipantRow,{...props,chemistryEnabled:false});
  assert.ok(withoutChemistry.includes('Engineering'));
  assert.doesNotMatch(withoutChemistry,/Pioneer|Guardian/);
  assert.equal(JSON.stringify(participant),before,'Rendering does not mutate participant attributes.');
});

test('redesigned group and room headers retain names and exact occupancy without adding staff categories',()=>{
  const source={title:'Room 3 — Single Occupancy',count:1,index:3,activityId:'hotel',room:{className:'hotel-room-neutral',warning:'Gender is not recorded for every occupant; this room has a neutral appearance.'}};
  const before=JSON.stringify(source);
  const occupant=React.createElement(ParticipantRow,{index:1,name:'Fictional Faculty',role:'Faculty',chemistryEnabled:false});
  const markup=render(AllocationGroupCard,{...source,children:occupant});
  assert.match(markup,/>Room 3<\/h3>/);
  assert.match(markup,/Single occupancy · 1 occupant/);
  assert.match(markup,/hotel-room-neutral/);
  assert.match(markup,/Fictional Faculty/);
  assert.doesNotMatch(markup,/University category:|Gender:|h-full/);
  assert.equal(JSON.stringify(source),before,'Room presentation does not change the saved room name.');
  const group=render(AllocationGroupCard,{title:'Group 2',count:6,index:2,activityId:'main'});
  assert.match(group,/6 participants/);
});

test('compact hotel summary retains all occupancy counts and faculty headings expose only their name',()=>{
  const summary={total_rooms:10,new_hire_shared:3,new_hire_analyst_shared:1,new_hire_single:1,support_lead_single:2,analyst_support_single:0,faculty_single:3};
  const markup=render(HotelResultsSummary,{summary});
  for(const label of ['Total rooms required','New-hire shared','New hire + Analyst Support','Single new hires','Single Support Leads','Single Analyst Support','Single faculty'])assert.ok(markup.includes(label),label);
  assert.match(markup,/>10<\/strong>/);
  const header=render(FacultyScheduleHeader,{name:'Fictional Faculty'});
  assert.match(header,/Fictional Faculty/);
  assert.doesNotMatch(header,/Offering|Engineering|chronological|assigned/);
});
