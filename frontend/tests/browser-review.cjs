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
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'aip-local-review-'));
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
    await page.getByRole('button', {name: 'Continue to Group Sizes', exact: true}).click();
    console.log('Passed faculty/support setup and male-only prayer selection');
    const optimized = page.waitForResponse(response => response.url().endsWith('/api/optimize') && response.request().method() === 'POST', {timeout: 60000});
    await page.getByRole('button', {name: 'Generate Week 2 Allocations', exact: true}).click();
    const response = await optimized;
    assert.equal(response.status(), 200, await response.text());
    const generated = await response.json();
    console.log('Generated all six allocations');
    const submitted = response.request().postDataJSON();
    assert.equal(submitted.configuration.reflection_settings.selected_participant_ids.length, 10);
    const labels = ['Main Groups', 'Quiz Night', 'Team Building', 'BUS Teams', 'My Reflections', 'Hotel Rooms'];
    await page.getByRole('button', {name: 'Edit Teams', exact: true}).waitFor();
    const legend = page.getByLabel('Results color legend', {exact: true});
    assert.ok((await legend.innerText()).includes('Public') && (await legend.innerText()).includes('Private'));
    assert.doesNotMatch(await legend.innerText(), /National|International|Other|Unclassified/);
    for (const label of labels) {
      await page.getByRole('button', {name: label, exact: true}).click();
      const rows = await page.locator('main .result-person-row').evaluateAll(elements => elements.filter(element => element.querySelector('[aria-label^="University category:"]')).map(element => ({
        text: element.innerText, color: getComputedStyle(element).backgroundColor,
        category: element.querySelector('[aria-label^="University category:"]').getAttribute('aria-label'),
      })));
      assert.equal(rows.length, 30, `${label}: all hire rows have university markers`);
      assert.ok(rows.every(row => /Public|Private/.test(row.category)), label);
      if (label !== 'Hotel Rooms') {
        assert.ok(rows.every(row => row.color !== 'rgba(0, 0, 0, 0)' && row.color !== 'rgb(255, 255, 255)'), `${label}: full rows colored`);
        const male = rows.find(row => row.text.includes('Browser Hire 01'));
        const female = rows.find(row => row.text.includes('Browser Hire 16'));
        assert.notEqual(male.color, female.color, `${label}: gender backgrounds differ`);
      } else {
        const rooms = await page.locator('article.hotel-room').evaluateAll(elements => elements.map(element => ({
          text: element.innerText, color: getComputedStyle(element).backgroundColor,
        })));
        assert.ok(rooms.some(room => /Browser Hire 0[1-7]/.test(room.text) && room.color !== 'rgb(255, 255, 255)' && room.color !== 'rgba(0, 0, 0, 0)'), 'Whole occupied hotel card is colored');
        assert.ok(rooms.some(room => room.text.includes('Faculty')), 'Faculty single rooms visible');
      }
      await page.screenshot({path: path.join(output, `${label.toLowerCase().replaceAll(' ', '-')}.png`), fullPage: true});
      console.log(`Passed ${label} result rows`);
    }
    for(const width of [834,390]){
      await page.setViewportSize({width,height:1000});
      for(const label of labels){
        await page.getByRole('button',{name:label,exact:true}).click();
        const geometry=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth,rows:document.querySelectorAll('.results-root .result-person-row').length}));
        assert.ok(geometry.page<=width+1,`${label}, Chemistry off, ${width}px: no page overflow`);
        assert.ok(geometry.rows>=30,`${label}, Chemistry off, ${width}px: participant information retained`);
        if(label==='My Reflections')assert.equal(await page.locator('.reflection-chemistry-cell.is-empty').first().evaluate(e=>getComputedStyle(e).display),'none','Mobile schedule omits unused Chemistry cells');
        await page.screenshot({path:path.join(output,`chemistry-off-${width}-${label.toLowerCase().replaceAll(' ','-')}.png`),fullPage:false});
      }
      console.log(`Passed all six tabs with Chemistry off at ${width}px`);
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('button', {name: 'My Reflections', exact: true}).click();
    assert.equal(await page.getByText('Appointments in chronological order', {exact: true}).count(), 0);
    assert.equal(await page.getByText('Faculty offering:', {exact: false}).count(), 0);
    for (const member of source.faculty_members) await page.getByRole('heading', {name: member.name, exact: true}).waitFor();
    const completion = generated.allocation.activities.find(activity => activity.activity_id === 'reflection').sessions.reduce((latest, session) => clock(session.end_time) > clock(latest) ? session.end_time : latest, '12:00 AM');
    await page.getByText('Completion Time', {exact: true}).waitFor();
    assert.ok((await page.getByText('Completion Time', {exact: true}).locator('..').innerText()).includes(completion));
    const stats = page.getByLabel('My Reflections statistics', {exact: true});
    const statisticsText = await stats.innerText();
    assert.match(statisticsText, /Participants/);
    assert.match(statisticsText, /Completion Time/);
    assert.doesNotMatch(statisticsText, /Accommodation Requested|Before Prayer|Offering Match|After Prayer/);
    const reflection = generated.allocation.activities.find(activity => activity.activity_id === 'reflection');
    const selected = new Set(submitted.configuration.reflection_settings.selected_participant_ids);
    const group = reflection.groups.find(item => item.participant_ids.filter(id => selected.has(id)).length >= 2);
    const [first, second] = group.participant_ids.filter(id => selected.has(id));
    async function swap() {
      const panel = page.getByRole('heading', {name: 'Edit My Reflections', exact: true}).locator('..');
      await panel.locator('select').nth(0).selectOption(first);
      await panel.locator('select').nth(1).selectOption(second);
      const edited = page.waitForResponse(item => item.url().endsWith('/api/allocations/edit'));
      await page.getByRole('button', {name: 'Switch Participants', exact: true}).click();
      assert.equal((await edited).status(), 200);
      await page.getByRole('button', {name: 'Undo Last Change', exact: true}).waitFor({state: 'visible'});
    }
    await page.getByRole('button', {name: 'Edit Teams', exact: true}).click();
    const dragSource = page.getByRole('button', {name: `Drag participant ${first}`, exact: true});
    const dragTarget = page.getByRole('button', {name: `Drag participant ${second}`, exact: true});
    await dragSource.scrollIntoViewIfNeeded();
    await dragTarget.scrollIntoViewIfNeeded();
    const sourceBox = await dragSource.boundingBox();
    const targetBox = await dragTarget.boundingBox();
    assert.ok(sourceBox && targetBox, 'Both appointment drag handles are visible');
    const dragged = page.waitForResponse(item => item.url().endsWith('/api/allocations/edit'), {timeout: 10000});
    await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(sourceBox.x + sourceBox.width / 2 + 8, sourceBox.y + sourceBox.height / 2 + 8, {steps: 3});
    await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, {steps: 15});
    await page.screenshot({path: path.join(output, 'appointment-dragging.png'), fullPage: false});
    await page.mouse.up();
    assert.equal((await dragged).status(), 200, 'Dragging two valid appointments swaps their slots');
    await page.getByRole('button', {name: 'Undo Last Change', exact: true}).click();
    const otherFaculty=reflection.groups.find(item=>item.id!==group.id&&item.participant_ids.some(id=>selected.has(id)));
    const crossParticipant=otherFaculty.participant_ids.find(id=>selected.has(id));
    await page.setViewportSize({width:1440,height:2600});
    const crossSource=page.getByRole('button',{name:`Drag participant ${first}`,exact:true});
    const crossTarget=page.getByRole('button',{name:`Drag participant ${crossParticipant}`,exact:true});
    await crossSource.scrollIntoViewIfNeeded();await crossTarget.scrollIntoViewIfNeeded();
    const crossSourceBox=await crossSource.boundingBox(),crossTargetBox=await crossTarget.boundingBox();
    assert.ok(crossSourceBox&&crossTargetBox);
    const crossDrag=page.waitForResponse(item=>item.url().endsWith('/api/allocations/edit'),{timeout:10000});
    await page.mouse.move(crossSourceBox.x+crossSourceBox.width/2,crossSourceBox.y+crossSourceBox.height/2);
    await page.mouse.down();
    await page.mouse.move(crossSourceBox.x+crossSourceBox.width/2+8,crossSourceBox.y+crossSourceBox.height/2+8,{steps:3});
    await page.mouse.move(crossTargetBox.x+crossTargetBox.width/2,crossTargetBox.y+crossTargetBox.height/2,{steps:20});
    await page.screenshot({path:path.join(output,'cross-faculty-dragging.png'),fullPage:false});
    await page.mouse.up();
    assert.equal((await crossDrag).status(),200,'Cross-faculty dragging exchanges two valid appointments');
    await page.getByRole('button',{name:'Undo Last Change',exact:true}).click();
    await page.setViewportSize({width:1440,height:1000});
    const protectedPerson = reflection.sessions.find(session => selected.has(session.participant_id) && clock(session.start_time) >= 780);
    const protectedSlot = reflection.sessions.find(session => !selected.has(session.participant_id) && clock(session.start_time) < 780 && clock(session.end_time) > 700);
    assert.ok(protectedPerson && protectedSlot, 'Mixed prayer cohort exercises unrestricted appointments during the break');
    const blockedPanel = page.getByRole('heading', {name: 'Edit My Reflections', exact: true}).locator('..');
    await blockedPanel.locator('select').nth(0).selectOption(protectedPerson.participant_id);
    await blockedPanel.locator('select').nth(1).selectOption(protectedSlot.participant_id);
    const blocked = page.waitForResponse(item => item.url().endsWith('/api/allocations/edit'));
    await page.getByRole('button', {name: 'Switch Participants', exact: true}).click();
    assert.equal((await blocked).status(), 422);
    assert.ok(await page.getByRole('button', {name: 'Undo Last Change', exact: true}).isDisabled());
    await swap();
    await page.getByRole('button', {name: 'Undo Last Change', exact: true}).click();
    assert.ok(await page.getByRole('button', {name: 'Undo Last Change', exact: true}).isDisabled());
    await page.getByRole('button', {name: 'Cancel Changes', exact: true}).click();
    await page.getByRole('button', {name: 'Edit Teams', exact: true}).click();
    await swap();
    await page.getByRole('button', {name: 'Reset to Generated', exact: true}).click();
    await swap();
    await page.getByRole('button', {name: 'Save Changes', exact: true}).click();
    await page.getByRole('button', {name: 'Edit Teams', exact: true}).waitFor();
    for (const label of ['Editable Excel', 'Final PDF']) {
      const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', {name: label, exact: true}).click()]);
      await download.saveAs(path.join(output, download.suggestedFilename()));
      assert.equal(await download.failure(), null, label);
    }
    await page.getByRole('button', {name: 'Individual PDF', exact: true}).click();
    const [privateManifest] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', {name: 'Hotel Rooms', exact: true}).last().click()]);
    await privateManifest.saveAs(path.join(output, privateManifest.suggestedFilename()));
    assert.equal(await privateManifest.failure(), null);
    await page.getByRole('button', {name: 'Hotel Rooms', exact: true}).click();
    await page.getByRole('button', {name: 'Edit Teams', exact: true}).click();
    await page.getByRole('checkbox', {name: /Allow accommodation-policy override confirmations/}).check();
    const hotelPanel = page.getByRole('heading', {name: 'Edit Hotel Rooms', exact: true}).locator('..');
    await hotelPanel.locator('select').nth(0).selectOption('B0');
    await hotelPanel.locator('select').nth(1).selectOption('B15');
    await page.getByRole('button', {name: 'Switch Participants', exact: true}).click();
    await page.getByRole('alertdialog').waitFor();
    const mixedEdit = page.waitForResponse(item => item.url().endsWith('/api/allocations/edit'));
    await page.getByRole('button', {name: 'Override & Save', exact: true}).click();
    assert.equal((await mixedEdit).status(), 200);
    const neutralRooms = page.locator('.hotel-room-neutral').filter({hasText: 'Mixed-gender room:'});
    await neutralRooms.first().waitFor();
    assert.equal(await neutralRooms.count(), 2, 'Both permitted mixed rooms have neutral cards and explicit warnings');
    await page.screenshot({path: path.join(output, 'hotel-approved-mixed-draft.png'), fullPage: true});
    await page.getByRole('button', {name: 'Cancel Changes', exact: true}).click();
    assert.deepEqual(runtimeErrors, []);
    console.log(JSON.stringify({passed: true, participants: 30, selectedMales: 10, checked: ['upload/import', 'cached nonbinary mapping migration', 'male prayer list', 'six allocation tabs', 'row colors and binary markers', 'whole hotel cards', 'simplified My Reflections', 'same-faculty and cross-faculty drag-and-drop', 'protected swap rejection', 'switch/undo/cancel/reset/save', 'Excel/public PDF/private hotel downloads', 'permitted mixed-room neutral warning'], artifacts: output}, null, 2));
  } catch (error) {
    await page.screenshot({path: path.join(output, 'failure.png'), fullPage: true}).catch(() => {});
    await fs.writeFile(path.join(output, 'failure.txt'), await page.locator('body').innerText()).catch(() => {});
    console.error(`Browser failure artifacts: ${output}`);
    throw error;
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
