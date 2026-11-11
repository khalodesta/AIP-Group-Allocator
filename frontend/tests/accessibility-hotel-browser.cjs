/* Local-only browser smoke. Requires Playwright and a locally installed Chrome.
 * Run with the API on :8000 and Next.js on :3000:
 * AIP_PLAYWRIGHT_PATH=/tmp/aip-browser/node_modules/playwright node tests/browser-review.cjs
 * The script uses an isolated browser context and fictional data only.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.AIP_PLAYWRIGHT_PATH || 'playwright');
const site = process.env.AIP_BROWSER_URL || 'http://localhost:3000';
const api = process.env.AIP_BROWSER_API || 'http://localhost:8000';

async function post(route, body, binary = false) {
  const response = await fetch(`${api}${route}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  assert.ok(response.ok, `${route}: ${response.status} ${response.ok ? '' : await response.text()}`);
  return binary ? Buffer.from(await response.arrayBuffer()) : response.json();
}
function clock(value) {
  const [, hour, minute, suffix] = value.match(/^(\d+):(\d+) (AM|PM)$/);
  return (Number(hour) % 12 + (suffix === 'PM' ? 12 : 0)) * 60 + Number(minute);
}

(async () => {
  const output = process.env.AIP_BROWSER_OUTPUT || await fs.mkdtemp(path.join(os.tmpdir(), 'aip-feature-review-')); await fs.mkdir(output,{recursive:true});
  const universities = ['Cairo University', 'Ain Shams University', 'German University in Cairo', 'American University in Cairo'];
  const offerings = ['Cyber', 'Customer', 'Engineering'];
  const source = {
    participants: Array.from({length: 30}, (_, i) => ({id: `B${i}`, name: `Browser Hire ${String(i + 1).padStart(2, '0')}`,
      attributes: {Gender: i < 15 ? 'Male' : 'Female', University: i === 0 ? 'Fictional Saved Academy' : i === 1 ? 'FSA' : universities[i % 4], 'L3 Offering': offerings[i % 3]}})),
    faculty_members: offerings.map((offering, i) => ({id: `F${i}`, name: `Browser Faculty ${i + 1}`, offering})),
    support_members: [
      {id: 'S0', name: 'Browser Lead One', gender: 'Male', category: 'Support Lead'},
      {id: 'S1', name: 'Browser Lead Two', gender: 'Female', category: 'Support Lead'},
      {id: 'S2', name: 'Browser Analyst One', gender: 'Male', category: 'Analyst Support'},
      {id: 'S3', name: 'Browser Analyst Two', gender: 'Female', category: 'Analyst Support'},
    ],
    configuration: {activities: [{id: 'main', name: 'Main Groups', mode: 'max_size', value: 4},
      {id: 'quiz', name: 'Quiz Night', mode: 'max_size', value: 4}, {id: 'team', name: 'Team Building', mode: 'max_size', value: 4}],
      time_limit_seconds: 2,
      custom_universities: [{id: 'custom:fictional saved academy', name: 'Fictional Saved Academy', aliases: ['FSA'], category: 'public'}],
      reflection_settings: {enabled: true, start_time: '11:15', prayer_deadline: '11:40',
        resume_time: '13:00', session_duration_minutes: 20, selected_participant_ids: Array.from({length: 10}, (_, i) => `B${i}`)}},
  };
  const initial = await post('/api/optimize', source);
  const workbook = await post('/api/export/editable', {...source, allocation: initial.allocation}, true);
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
  await context.addInitScript(() => {
    const key = 'aip-university-directory-v1';
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({schema_version: 1, universities: [
      {id: 'custom:fictional saved academy', name: 'Fictional Saved Academy', aliases: ['FSA'], category: 'national'},
    ]}));
  });
  const page = await context.newPage();
  const privacyViolations=[];let apiCalls=0;
  page.on('request',request=>{if(request.url().includes('/api/')){apiCalls++;const body=request.postData();if(body&&/accessibilityIds|accessibility_flags|disability|flaggedParticipant/i.test(body))privacyViolations.push(request.url());}});
  page.setDefaultTimeout(20000);
  const runtimeErrors = [];
  page.on('pageerror', error => runtimeErrors.push(error.message));
  page.on('dialog', dialog => dialog.accept());
  try {
    await page.goto(site, {waitUntil: 'networkidle'});
    await page.addStyleTag({content:'nextjs-portal{display:none!important}'});
    await page.getByRole('checkbox', {name: /Include Business Chemistry in group allocation/}).uncheck();
    await page.locator('input[type="file"]').first().setInputFiles({name: 'fictional-master.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: workbook});
    await page.getByText('30 records', {exact: true}).waitFor();
    const category = page.getByRole('combobox', {name: 'Category for Fictional Saved Academy', exact: true});
    await category.waitFor();
    assert.equal(await category.count(), 1, 'Old alias mappings require one review per institution');
    assert.deepEqual(await category.locator('option').evaluateAll(options => options.map(option => option.value)), ['', 'public', 'private']);
    assert.equal(await category.inputValue(), '', 'Old nonbinary category must not be guessed');
    await category.selectOption('public');
    await category.locator('..').getByRole('button', {name: 'Confirm', exact: true}).click();
    const cached = await page.evaluate(() => JSON.parse(localStorage.getItem('aip-university-directory-v1')));
    assert.equal(cached.universities[0].category, 'public');
    assert.ok(cached.universities[0].aliases.includes('FSA'), 'Confirmation preserves every cached institution alias');
    assert.deepEqual(cached.pending_review, []);
    assert.equal(await page.getByRole('combobox', {name: /^Category for /}).count(), 0, 'No alias remains unresolved after confirming its institution');
    console.log('Passed upload and cached directory migration');
    await checkFlags();
    await setupScreens('upload');
    await page.getByRole('button', {name: 'Continue to Faculty & Support', exact: true}).click();
    for (let i = 0; i < 3; i++) {
      await page.getByPlaceholder(`Faculty ${i + 1} name`, {exact: true}).fill(source.faculty_members[i].name);
      const offering = page.getByRole('combobox', {name: `Faculty ${i + 1} offering`, exact: true});
      await offering.fill(offerings[i]);
      await offering.press('Enter');
    }
    assert.equal(await page.getByText('Faculty availability', {exact: true}).count(), 0);
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.getByRole('button', {name: 'Import support Excel', exact: true}).click()]);
    await chooser.setFiles({name: 'fictional-staff.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: workbook});
    await page.getByRole('textbox', {name: 'Support member 4 name', exact: true}).waitFor();
    assert.equal(await page.getByRole('combobox', {name: 'Support member 1 category', exact: true}).inputValue(), 'Support Lead');
    await page.getByRole('checkbox', {name: /Enable My Reflections Time Optimization/}).check();
    for (const person of source.participants) {
      const selector = page.getByRole('checkbox', {name: person.name, exact: true});
      assert.equal(await selector.count(), person.attributes.Gender === 'Male' ? 1 : 0, person.name);
    }
    await page.getByRole('button', {name: 'Select All', exact: true}).click();
    for (const person of source.participants.slice(10, 15)) await page.getByRole('checkbox', {name: person.name, exact: true}).uncheck();
    await page.getByLabel('Start time', {exact: true}).fill('11:15');
    await page.getByLabel('Friday prayer start', {exact: true}).fill('11:40');
    await page.getByLabel('Post-prayer resume time', {exact: true}).fill('13:00');
    await setupScreens('faculty-support');
    await page.getByRole('button', {name: 'Continue to Group Sizes', exact: true}).click();
    await setupScreens('group-sizes');
    console.log('Passed faculty/support setup and male-only prayer selection');
    const optimized = page.waitForResponse(response => response.url().endsWith('/api/optimize') && response.request().method() === 'POST', {timeout: 60000});
    await page.getByRole('button', {name: 'Generate Week 2 Allocations', exact: true}).click();
    const response = await optimized;
    assert.equal(response.status(), 200, await response.text());
    const generated = await response.json();
    console.log('Generated all six allocations');
    const submitted = response.request().postDataJSON();
    assert.equal(submitted.configuration.reflection_settings.selected_participant_ids.length, 10);
    if(process.env.AIP_BASELINE_ALLOCATION){const original=JSON.parse(await fs.readFile(process.env.AIP_BASELINE_ALLOCATION,'utf8'));assert.deepEqual(submitted,original.request,'Flag selections do not change the optimizer request');}
    const labels=['Main Groups','Quiz Night','Team Building','BUS Teams','My Reflections','Hotel Rooms'];
    for(const label of labels){
      await page.getByRole('button',{name:label,exact:true}).click();
      assert.equal(await page.locator('.accessibility-indicator').count(),2,label);
      const flagged=await page.locator('.accessibility-indicator').evaluateAll(elements=>elements.map(icon=>icon.closest('.participant-identity').textContent));
      assert.ok(flagged.some(text=>text.includes('Browser Hire 01'))&&flagged.some(text=>text.includes('Browser Hire 16')),label);
      assert.equal(await page.getByRole('button',{name:'Add Room',exact:true}).count(),0);
    }
    console.log('Passed flags in all six Results tabs and unchanged optimizer input');
    const initialHotel=generated.allocation.activities.find(a=>a.activity_id==='hotel');
    const initialRooms=initialHotel.groups.length;
    await page.getByRole('button',{name:'Edit Teams',exact:true}).click();
    await page.getByRole('button',{name:'Add Room',exact:true}).click();
    let manual=await manualRooms();assert.equal(manual.length,1);
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    assert.equal((await manualRooms()).length,0,'Undo Add Room');
    for(let i=0;i<3;i++)await page.getByRole('button',{name:'Add Room',exact:true}).click();
    manual=await manualRooms();assert.equal(manual.length,3);
    assert.equal(new Set(manual.map(room=>room.id)).size,3);
    assert.equal(new Set(manual.map(room=>room.name)).size,3);
    assert.equal(Number(await page.locator('.hotel-total strong').innerText()),initialRooms,'Empty draft rooms are not bookings');
    const unused=manual[2];
    await roomCard(unused.id).getByRole('button',{name:`Remove ${unused.name}`,exact:true}).click();
    assert.equal((await manualRooms()).length,2);
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    assert.ok((await manualRooms()).some(room=>room.id===unused.id),'Undo Remove Room restores its ID');
    await roomCard(unused.id).getByRole('button',{name:`Remove ${unused.name}`,exact:true}).click();

    // An unrelated manual edit must survive a later hotel-only Reset.
    await page.getByRole('button',{name:'Main Groups',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'Add Room',exact:true}).count(),0);
    const mainPair=generated.allocation.activities.find(a=>a.activity_id==='main').groups[0].participant_ids.slice(0,2);
    await page.getByRole('combobox',{name:'First participant to switch',exact:true}).selectOption(mainPair[0]);
    await page.getByRole('combobox',{name:'Second participant to switch',exact:true}).selectOption(mainPair[1]);
    const mainEdited=await edit(()=>page.getByRole('button',{name:'Switch Participants',exact:true}).click());
    const expectedOther=mainEdited.allocation.activities.filter(a=>a.activity_id!=='hotel');
    await page.getByRole('button',{name:'Hotel Rooms',exact:true}).click();
    assert.equal((await manualRooms()).length,2,'Draft rooms survive activity navigation');
    const shared=initialHotel.groups.find(room=>room.participant_ids.length===2&&room.participant_ids.every(id=>submitted.participants.some(p=>p.id===id))&&room.participant_ids.includes('B0'))||initialHotel.groups.find(room=>room.participant_ids.length===2&&room.participant_ids.every(id=>submitted.participants.some(p=>p.id===id)));
    assert.ok(shared);
    const [moved,roommate]=shared.participant_ids;
    const target=manual[0];
    await page.setViewportSize({width:1440,height:6500});
    const sourceHandle=page.getByRole('button',{name:`Drag participant ${moved}`,exact:true});
    const destination=roomCard(target.id).locator('.hotel-empty-room');
    await destination.scrollIntoViewIfNeeded();await sourceHandle.scrollIntoViewIfNeeded();
    const from=await sourceHandle.boundingBox(),to=await destination.boundingBox();assert.ok(from&&to);
    const dragged=page.waitForResponse(response=>response.url().endsWith('/api/allocations/edit'));
    await page.mouse.move(from.x+from.width/2,from.y+from.height/2);await page.mouse.down();
    await page.mouse.move(from.x+from.width/2+8,from.y+from.height/2+8,{steps:3});
    await page.mouse.move(to.x+to.width/2,to.y+to.height/2,{steps:35});
    await page.mouse.up();await page.waitForTimeout(100); // dnd-kit click blocker lasts 50ms.
    const dragResponse=await dragged;assert.equal(dragResponse.status(),200,await dragResponse.text());
    assert.equal(dragResponse.request().postDataJSON().swap_with_id,null,'An empty-room drop is a genuine MOVE');
    await ready();
    assert.equal(await roomCard(shared.id).locator('[data-participant-id]').count(),1);
    assert.equal(await roomCard(target.id).locator('[data-participant-id]').count(),1);
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    await roomCard(target.id).getByText('Drag a participant here',{exact:true}).waitFor();
    assert.equal(await roomCard(shared.id).locator('[data-participant-id]').count(),2,'Undo Move restores both rooms');
    await page.setViewportSize({width:1440,height:1000});
    await movePerson(moved,target.id);
    assert.equal(await roomCard(target.id).getByRole('button',{name:/Remove/}).count(),0,'Occupied rooms cannot be deleted');
    await movePerson(roommate,target.id);
    assert.equal(await roomCard(target.id).locator('[data-participant-id]').count(),2,'Move into a one-person room');
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    await roomCard(shared.id).locator(`[data-participant-id="${roommate}"]`).waitFor();
    await page.getByRole('combobox',{name:'First participant to switch',exact:true}).selectOption(moved);
    await page.getByRole('combobox',{name:'Second participant to switch',exact:true}).selectOption(roommate);
    await edit(()=>page.getByRole('button',{name:'Switch Participants',exact:true}).click());
    await roomCard(target.id).locator(`[data-participant-id="${roommate}"]`).waitFor();
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    await roomCard(target.id).locator(`[data-participant-id="${moved}"]`).waitFor();
    assert.equal(await page.getByRole('button',{name:'Editable Excel',exact:true}).count(),0,'Drafts are not exported');
    const validation=page.waitForRequest(request=>request.url().endsWith('/api/allocations/validate'));
    await page.getByRole('button',{name:'Save Changes',exact:true}).click();
    const saved=(await validation).postDataJSON();
    await page.getByRole('button',{name:'Edit Teams',exact:true}).waitFor();
    const savedHotel=saved.allocation.activities.find(a=>a.activity_id==='hotel');
    assert.ok(savedHotel.groups.every(room=>room.participant_ids.length>0));
    assert.equal(savedHotel.groups.length,initialRooms+1);
    assert.deepEqual(saved.allocation.activities.filter(a=>a.activity_id!=='hotel'),expectedOther);
    assert.equal(Number(await page.locator('.hotel-total strong').innerText()),initialRooms+1);
    assert.equal(await page.locator('.results-notice').count(),0,'Intentional singles have no optimization warning');
    assert.equal(await page.locator('.accessibility-indicator').count(),2);
    await fs.writeFile(path.join(output,'saved-manifest.json'),JSON.stringify(saved,null,2));
    await page.screenshot({path:path.join(output,'hotel-saved-private-room.png'),fullPage:true});
    await exportFile('Editable Excel','/api/export/editable','saved-hotel.xlsx',saved.allocation);
    await exportFile('Final PDF','/api/export/pdf','saved-public.pdf',saved.allocation);
    await page.getByRole('button',{name:'Individual PDF',exact:true}).click();
    const privateRequest=page.waitForRequest(request=>request.url().endsWith('/api/export/pdf/hotel'));
    const [privatePdf]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Hotel Rooms',exact:true}).last().click()]);
    assert.deepEqual((await privateRequest).postDataJSON().allocation,saved.allocation);
    await privatePdf.saveAs(path.join(output,'saved-private-hotel.pdf'));assert.equal(await privatePdf.failure(),null);

    // Reopen, change several draft operations, then Cancel back to saved rooms.
    await page.getByRole('button',{name:'Edit Teams',exact:true}).click();
    assert.ok((await manualRooms()).some(room=>room.id===target.id));
    await page.getByRole('button',{name:'Add Room',exact:true}).click();
    await page.getByRole('button',{name:'Add Room',exact:true}).click();
    const cancelled=(await manualRooms()).filter(room=>room.id!==target.id);
    await movePerson(moved,cancelled[0].id);
    await page.getByRole('button',{name:'Cancel Changes',exact:true}).click();
    await roomCard(target.id).locator(`[data-participant-id="${moved}"]`).waitFor();
    assert.equal((await manualRooms()).length,1);
    await page.getByRole('button',{name:'Main Groups',exact:true}).click();
    await page.getByRole('button',{name:'Hotel Rooms',exact:true}).click();
    await page.getByRole('button',{name:'Edit Teams',exact:true}).click();
    await page.getByRole('button',{name:'Reset to Generated',exact:true}).click();
    assert.equal((await manualRooms()).length,0);
    await page.getByRole('button',{name:'Main Groups',exact:true}).click();
    const firstGroup=expectedOther.find(a=>a.activity_id==='main').groups[0];
    const rendered=await page.locator(`[data-group-id="${firstGroup.id}"] [data-participant-id]`).evaluateAll(rows=>rows.map(row=>row.dataset.participantId));
    assert.deepEqual(rendered,firstGroup.participant_ids,'Hotel Reset preserves the unrelated manual Main edit');
    await page.getByRole('button',{name:'Hotel Rooms',exact:true}).click();
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    assert.equal((await manualRooms()).length,1,'Undo Reset restores saved manual room');
    await page.getByRole('button',{name:'Cancel Changes',exact:true}).click();
    assert.deepEqual(privacyViolations,[],'Flags never leave frontend state');
    assert.deepEqual(runtimeErrors,[]);
    console.log(JSON.stringify({passed:true,checked:['flags select/search/deselect/save/cancel/rename/delete/clear/replacement','all six Results indicators','unchanged optimization payload','Add/Remove rooms','drag MOVE','keyboard MOVE','one-person destination','Undo Add/Move/Swap/Remove/Reset','Cancel multiple changes','Save discards empty rooms','authoritative saved exports','hotel-only Reset','no flag payloads'],artifacts:output},null,2));

    async function setupScreens(label){
      for(const width of [1440,834,390]){
        await page.setViewportSize({width,height:1000});
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${label}: no horizontal page overflow at ${width}`);
        await page.screenshot({path:path.join(output,`${label}-${width}.png`),fullPage:true});
      }
      await page.setViewportSize({width:1440,height:1000});
    }
    async function checkFlags(){
      const button=page.getByRole('button',{name:'Accessibility Flags',exact:true});
      const dialog=page.getByRole('dialog',{name:'Accessibility Flags',exact:true});
      const open=async()=>{await button.click();await dialog.waitFor();};
      const checkbox=name=>dialog.locator('label.accessibility-person').filter({hasText:name}).getByRole('checkbox');
      const save=async()=>{const calls=apiCalls;await dialog.getByRole('button',{name:'Save Flags',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.equal(apiCalls,calls,'Saving flags performs no API request');};
      await open();await dialog.getByText('0 selected',{exact:true}).waitFor();
      await dialog.getByRole('searchbox',{name:'Search new hires',exact:true}).fill('Browser Hire 01');await checkbox('Browser Hire 01').check();await save();
      await open();await dialog.getByRole('searchbox',{name:'Search new hires',exact:true}).fill('Browser Hire 16');await checkbox('Browser Hire 16').check();await save();
      await open();await checkbox('Browser Hire 16').uncheck();await checkbox('Browser Hire 03').check();await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
      await open();assert.ok(await checkbox('Browser Hire 01').isChecked());assert.ok(await checkbox('Browser Hire 16').isChecked());assert.ok(!await checkbox('Browser Hire 03').isChecked());
      await checkbox('Browser Hire 16').uncheck();await save();await open();assert.ok(!await checkbox('Browser Hire 16').isChecked());await checkbox('Browser Hire 16').check();await save();
      await page.getByRole('textbox',{name:'Name for participant 1',exact:true}).fill('Browser Hire 01 Renamed');
      await open();await dialog.getByRole('searchbox',{name:'Search new hires',exact:true}).fill('Renamed');assert.ok(await checkbox('Browser Hire 01 Renamed').isChecked());await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
      await page.getByRole('textbox',{name:'Name for participant 1',exact:true}).fill('Browser Hire 01');
      await open();await checkbox('Browser Hire 30').check();await save();
      await page.getByRole('button',{name:'Delete Browser Hire 30',exact:true}).click();
      await open();await dialog.getByText('2 selected',{exact:true}).waitFor();await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
      await page.locator('input[type=file]').first().setInputFiles({name:'replacement-fictional-cohort.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});
      await page.getByText('30 records',{exact:true}).waitFor();
      await open();await dialog.getByText('0 selected',{exact:true}).waitFor();await checkbox('Browser Hire 01').check();await save();
      await page.getByRole('button',{name:'Clear All',exact:true}).click();
      await open();await dialog.getByText('0 selected',{exact:true}).waitFor();await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
      const imported=page.waitForResponse(response=>response.url().endsWith('/api/upload'));
      await page.locator('input[type=file]').first().setInputFiles({name:'restored-fictional-cohort.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});await imported;
      await page.waitForFunction(()=>document.querySelector('input[aria-label="Name for participant 1"]')?.value==='Browser Hire 01');
      await open();await checkbox('Browser Hire 01').check();await checkbox('Browser Hire 16').check();
      await page.screenshot({path:path.join(output,'accessibility-flags-modal.png'),fullPage:false});await save();
    }
    function roomCard(id){return page.locator(`[data-group-id="${id}"]`);}
    async function manualRooms(){return page.locator('[data-group-id^="hotel-manual-"]').evaluateAll(elements=>elements.map(element=>({id:element.dataset.groupId,name:element.querySelector('h3').textContent})));}
    async function ready(){await page.waitForFunction(()=>{const button=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='Save Changes');return button&&!button.disabled;});}
    async function edit(action){const pending=page.waitForResponse(response=>response.url().endsWith('/api/allocations/edit'));await action();const response=await pending;assert.equal(response.status(),200,await response.text());const body=await response.json();assert.ok(!body.requires_confirmation,JSON.stringify(body.conflicts));await ready();return body;}
    async function movePerson(id,room){await page.getByRole('combobox',{name:'First participant to switch',exact:true}).selectOption(id);await page.getByLabel('Move the first selected person to a room',{exact:true}).selectOption(room);return edit(()=>page.getByRole('button',{name:'Move Participant',exact:true}).click());}
    async function exportFile(label,route,name,allocation){const request=page.waitForRequest(request=>request.url().endsWith(route));const [file]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:label,exact:true}).click()]);assert.deepEqual((await request).postDataJSON().allocation,allocation);await file.saveAs(path.join(output,name));assert.equal(await file.failure(),null);}
  }catch(error){
    await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
    await fs.writeFile(path.join(output,'failure.txt'),await page.locator('body').innerText()).catch(()=>{});
    console.error('Feature browser failure artifacts: '+output);throw error;
  }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
