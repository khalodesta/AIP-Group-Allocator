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
const {ParticipantIdentity,ResultsLegend} = require('../components/ParticipantIdentity.tsx');
const {UniversityReview} = require('../components/UniversityReview.tsx');
const {classifyUniversity,classifiedParticipants,mergedUniversityDirectory,parseCustomDirectory} = require('../components/universityClassification.ts');
const {hotelRoomSummary} = require('../components/hotelSummary.ts');
const directory = JSON.parse(fs.readFileSync(path.join(__dirname,'../backend/data/university_directory.json'),'utf8')).universities;
const person=(id,university='Cairo University',gender='Male')=>({id,name:`Fictional ${id}`,attributes:{University:university,Gender:gender}});
const render=(Component,props={})=>renderToStaticMarkup(React.createElement(Component,props));

test('official classification and Capital-Helwan aliases retain National institution distinction',()=>{
  assert.equal(classifyUniversity('CU',directory,[]),'public');
  assert.equal(classifyUniversity('GUC',directory,[]),'private');
  assert.equal(classifyUniversity('Helwan National University',directory,[]),'national');
  assert.equal(classifyUniversity('UPEI Cairo',directory,[]),'international');
  assert.equal(classifyUniversity('Fictional Unknown Academy',directory,[]),undefined);
  const classified=classifiedParticipants([person('1','Helwan University'),person('2','Capital University'),person('3','جامعة العاصمة'),person('4','Helwan National University')],directory,[]);
  assert.deepEqual(classified.slice(0,3).map(p=>p.attributes.University),Array(3).fill('Capital-Helwan University'));
  assert.equal(classified[3].attributes.University,'Helwan National University');
});
test('custom confirmation applies once to normalized aliases and overrides known category',()=>{
  const entries=parseCustomDirectory({universities:[{id:'custom:fictional academy',name:'Fictional Academy',aliases:['FA','Fictional-Academy'],category:'national'},{id:'eg-cairo-university',name:'Cairo University',aliases:['CU'],category:'other'}]});
  assert.equal(classifyUniversity(' fA ',directory,entries),'national');
  assert.equal(classifyUniversity('Fictional-Academy',directory,entries),'national');
  assert.equal(classifyUniversity('Cairo University',directory,entries),'other');
  const merged=mergedUniversityDirectory(directory,entries);
  assert.equal(merged.filter(u=>u.id==='eg-cairo-university').length,1);
  assert.equal(merged.find(u=>u.id==='custom:fictional academy').diversity_category,'national');
});
test('directory import validates IDs, categories, and repeated aliases',()=>{
  assert.throws(()=>parseCustomDirectory({universities:[{id:'one',name:'Fictional Academy',aliases:[],category:'toString'}]}),/supported category/);
  assert.throws(()=>parseCustomDirectory([{id:'one',name:'First',aliases:['FA'],category:'public'},{id:'two',name:'Second',aliases:['fa'],category:'private'}]),/more than one/);
  assert.throws(()=>parseCustomDirectory([{id:'same',name:'First',aliases:[],category:'public'},{id:'same',name:'Second',aliases:[],category:'private'}]),/duplicate/);
});
test('classification review prompts once per unique university and never guesses a category',()=>{
  const markup=render(UniversityReview,{people:[person('1','Fictional Academy'),person('2','fictional-academy')],directory,custom:[],confirm:()=>true});
  assert.match(markup,/University classification required/);
  assert.match(markup,/Confirm 1 unique university/);
  assert.equal((markup.match(/Category for Fictional Academy/g)||[]).length,1);
  assert.match(markup,/<option value="" selected="">Choose category<\/option>/);
});
test('shared participant identity conveys gender and category with distinct accessible styling',()=>{
  for(const gender of ['Male','Female'])for(const category of ['public','private','national','international','other']){
    const markup=render(ParticipantIdentity,{name:'Fictional Person',gender,category});
    assert.match(markup,new RegExp(`person-gender-${gender.toLowerCase()}`));
    assert.match(markup,new RegExp(`university-${category}`));
    assert.match(markup,new RegExp(`Gender: ${gender}`));
    assert.match(markup,/aria-label="University category:/);
    assert.doesNotMatch(markup,/\(Male,|\(Female,/);
  }
});
test('support uses recorded gender and role; faculty attributes remain uninferred',()=>{
  const support=render(ParticipantIdentity,{name:'Fictional Helper',gender:'Female',role:'Analyst Support'});
  assert.match(support,/person-gender-female/);assert.match(support,/Analyst Support/);assert.doesNotMatch(support,/university-marker/);
  const faculty=render(ParticipantIdentity,{name:'Fictional Faculty',role:'Faculty'});
  assert.match(faculty,/person-gender-unknown/);assert.doesNotMatch(faculty,/Gender:|University category:/);
});
test('results legend names all gender and university category treatments',()=>{
  const markup=render(ResultsLegend);
  for(const label of ['Results color legend','Male','Female','Public','Private','National / Ahleya','International / Foreign Branch','Other / Needs Review'])assert.ok(markup.includes(label),label);
});
test('hotel summary counts actual unique rooms and every supported occupancy type',()=>{
  const people=Object.fromEntries(['p1','p2','p3','p4'].map(id=>[id,person(id)]));
  const support={a1:{id:'a1',name:'Fictional Analyst One',category:'Analyst Support'},a2:{id:'a2',name:'Fictional Analyst Two',category:'Analyst Support'},l1:{id:'l1',name:'Fictional Lead',category:'Support Lead'}};
  const faculty=[{id:'f1',name:'Fictional Faculty'}];
  const groups=[['p1','p2'],['p3','a1'],['p4'],['l1'],['a2'],['f1']].map((ids,index)=>({id:`room-${index}`,name:`Room ${index+1}`,participant_ids:ids}));
  const summary=hotelRoomSummary(groups,people,support,faculty);
  assert.deepEqual(summary,{total_rooms:6,new_hire_shared:1,new_hire_analyst_shared:1,new_hire_single:1,support_lead_single:1,analyst_support_single:1,faculty_single:1});
  assert.equal(Object.entries(summary).filter(([key])=>key!=='total_rooms').reduce((total,[,count])=>total+count,0),summary.total_rooms);
});

test('imported confirmed custom classifications survive editable Excel roundtrip',()=>{
  const imported=person('imported','Fictional Imported University');imported.attributes['University Category']='national';
  assert.equal(classifiedParticipants([imported],directory,[])[0].attributes['University Category'],'national');
  const markup=render(UniversityReview,{people:[imported],directory,custom:[],confirm:()=>true});
  assert.doesNotMatch(markup,/classification required/);assert.match(markup,/National \/ Ahleya/);
});
