/* Local visual QA with fictional data. Start localhost:3000 and :8000, then run:
 * AIP_PLAYWRIGHT_PATH=/tmp/aip-browser/node_modules/playwright node tests/results-responsive-review.cjs
 */
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {spawnSync}=require('node:child_process');
const {chromium}=require(process.env.AIP_PLAYWRIGHT_PATH||'playwright');
const site=process.env.AIP_BROWSER_URL||'http://localhost:3000';
const api=process.env.AIP_BROWSER_API||'http://localhost:8000';
async function post(route,body,binary=false){const response=await fetch(api+route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});assert.ok(response.ok,`${route}: ${response.status} ${response.ok?'':await response.text()}`);return binary?Buffer.from(await response.arrayBuffer()):response.json();}

(async()=>{
  const output=await fs.mkdtemp(path.join(os.tmpdir(),'aip-design-review-'));
  const catalog=await(await fetch(api+'/api/universities')).json();
  const academy=catalog.universities.find(item=>item.official_english_name==='Arab Academy for Science, Technology and Maritime Transport');
  assert.ok(academy);
  const custom=[{id:academy.id,name:academy.official_english_name,aliases:['AASTMT'],category:'public'}];
  const institutions=['AASTMT','Cairo University','German University in Cairo','American University in Cairo','October University for Modern Sciences and Arts','Capital-Helwan University'];
  const offerings=['Cyber','Customer','Engineering'], chemistry=['Pioneer','Driver','Guardian','Integrator'];
  const source={
    participants:Array.from({length:27},(_,i)=>({id:`D${i}`,name:`Fictional Hire ${String(i+1).padStart(2,'0')}`,attributes:{Gender:i<14?'Male':'Female',University:institutions[i%6],'L3 Offering':offerings[i%3],'Primary Chemistry':chemistry[i%4],'Secondary Chemistry':chemistry[(i+1)%4]}})),
    faculty_members:offerings.map((offering,i)=>({id:`F${i}`,name:`Fictional Faculty ${i+1}`,offering})),
    support_members:[{id:'S0',name:'Fictional Lead One',gender:'Male',category:'Support Lead'},{id:'S1',name:'Fictional Lead Two',gender:'Female',category:'Support Lead'},{id:'S2',name:'Fictional Analyst One',gender:'Male',category:'Analyst Support'},{id:'S3',name:'Fictional Analyst Two',gender:'Female',category:'Analyst Support'}],
    configuration:{activities:[['main','Main Groups'],['quiz','Quiz Night'],['team','Team Building']].map(([id,name])=>({id,name,mode:'max_size',value:6})),time_limit_seconds:2,include_business_chemistry:true,custom_universities:custom,reflection_settings:{enabled:true,start_time:'11:15',prayer_deadline:'11:40',resume_time:'13:00',session_duration_minutes:20,selected_participant_ids:Array.from({length:10},(_,i)=>`D${i}`)}}
  };
  const fixture=await post('/api/optimize',source);
  const workbook=await post('/api/export/editable',{...source,allocation:fixture.allocation},true);
  const chemistryFile=spawnSync(process.env.AIP_PYTHON||path.resolve('../.venv/bin/python'),['-c',"import io,json,sys;from openpyxl import Workbook;rows=json.load(sys.stdin);w=Workbook();s=w.active;s.append(['Name','Primary','Secondary']);[s.append(row) for row in rows];b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())"],{input:JSON.stringify(source.participants.map(p=>[p.name,p.attributes['Primary Chemistry'],p.attributes['Secondary Chemistry']])),maxBuffer:1024*1024});
  assert.equal(chemistryFile.status,0,chemistryFile.stderr.toString());
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.addInitScript(entries=>localStorage.setItem('aip-university-directory-v1',JSON.stringify({schema_version:2,universities:entries,pending_review:[]})),custom);
  const page=await context.newPage();page.setDefaultTimeout(20000);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
  let optimizations=0;page.on('request',request=>{if(request.url().endsWith('/api/optimize'))optimizations++;});
  try{
    await page.goto(site,{waitUntil:'networkidle'});
    await page.addStyleTag({content:'nextjs-portal{display:none!important}'});
    await page.locator('input[type=file]').nth(0).setInputFiles({name:'fictional-master.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});
    await page.getByText('27 records',{exact:true}).waitFor();
    const matching=page.waitForResponse(response=>response.url().endsWith('/api/chemistry/match'));
    await page.locator('input[type=file]').nth(1).setInputFiles({name:'fictional-chemistry.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:chemistryFile.stdout});
    const matched=await(await matching).json();assert.equal(matched.matched.length,27);assert.equal(matched.requires_review.length,0);
    await page.getByRole('button',{name:'Continue to Faculty & Support',exact:true}).click();
    for(let i=0;i<3;i++){await page.getByPlaceholder(`Faculty ${i+1} name`,{exact:true}).fill(source.faculty_members[i].name);const field=page.getByRole('combobox',{name:`Faculty ${i+1} offering`,exact:true});await field.fill(offerings[i]);await field.press('Enter');}
    const[chooser]=await Promise.all([page.waitForEvent('filechooser'),page.getByRole('button',{name:'Import support Excel',exact:true}).click()]);
    await chooser.setFiles({name:'fictional-support.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});
    await page.getByRole('textbox',{name:'Support member 4 name',exact:true}).waitFor();
    await page.getByRole('checkbox',{name:/Enable My Reflections Time Optimization/}).check();
    await page.getByRole('button',{name:'Select All',exact:true}).click();
    for(const person of source.participants.slice(10,14))await page.getByRole('checkbox',{name:person.name,exact:true}).uncheck();
    for(const[label,value]of[['Start time','11:15'],['Friday prayer start','11:40'],['Post-prayer resume time','13:00']])await page.getByLabel(label,{exact:true}).fill(value);
    await page.getByRole('button',{name:'Continue to Group Sizes',exact:true}).click();
    const pending=page.waitForResponse(response=>response.url().endsWith('/api/optimize')&&response.request().method()==='POST',{timeout:90000});
    await page.getByRole('button',{name:'Generate Week 2 Allocations',exact:true}).click();
    const response=await pending;assert.equal(response.status(),200,await response.text());const generated=(await response.json()).allocation;
    await page.getByRole('button',{name:'Edit Teams',exact:true}).waitFor();
    assert.deepEqual(generated.activities.find(a=>a.activity_id==='main').groups.map(g=>g.participant_ids.length).sort(),[5,5,5,6,6]);
    const labels=['Main Groups','Quiz Night','Team Building','BUS Teams','My Reflections','Hotel Rooms'], observations=[];
    for(const[width,height,device]of[[1440,1000,'desktop'],[834,1100,'tablet'],[390,844,'mobile']]){
      await page.setViewportSize({width,height});
      for(const activity of labels){
        await page.getByRole('button',{name:activity,exact:true}).click();
        await page.locator('.result-section-header h2').filter({hasText:activity}).waitFor();
        const metrics=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth,rows:document.querySelectorAll('.results-root .result-person-row').length,cards:[...document.querySelectorAll('.allocation-group-card')].map(e=>Math.round(e.getBoundingClientRect().width))}));
        assert.ok(metrics.page<=width+1,`${activity} ${device}: page overflow ${metrics.page}>${width}`);
        assert.ok(metrics.rows>=27,`${activity} ${device}: every participant is present`);
        if(activity==='Main Groups'){
          assert.equal(await page.locator('.participant-university').filter({hasText:academy.official_english_name}).count(),5);
          const long=await page.locator('.participant-university').filter({hasText:academy.official_english_name}).first().evaluate(e=>({scroll:e.scrollWidth,width:e.clientWidth}));
          assert.ok(long.scroll<=long.width+1,'Long names wrap within their records');
          assert.ok(await page.locator('.chemistry-segment').count()>=54,'Both Chemistry attributes remain available');
          const contrast=await page.locator('.result-record.result-gender-male').first().evaluate(row=>{
            const light=color=>{const values=color.match(/[\d.]+/g).slice(0,3).map(Number).map(value=>value/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);return values[0]*.2126+values[1]*.7152+values[2]*.0722;};
            const background=light(getComputedStyle(row).backgroundColor);
            return ['.person-name','.participant-university','.participant-offering'].map(selector=>{const color=light(getComputedStyle(row.querySelector(selector)).color);return{selector,ratio:(Math.max(color,background)+.05)/(Math.min(color,background)+.05)};});
          });
          assert.ok(contrast.every(item=>item.ratio>=4.5),`Participant text contrast: ${JSON.stringify(contrast)}`);
        }
        if(activity==='My Reflections'){
          assert.equal(await page.locator('.reflection-table tbody tr').count(),27);
          const text=await page.getByLabel('My Reflections statistics',{exact:true}).innerText();assert.match(text,/Participants/);assert.match(text,/Completion Time/);assert.doesNotMatch(text,/Accommodation|Before Prayer|After Prayer|Offering Match/);
          if(width<1000)assert.equal(await page.locator('.reflection-table tbody tr').first().evaluate(e=>getComputedStyle(e).display),'grid');
        }
        observations.push({activity,device,...metrics});
        await page.screenshot({path:path.join(output,`${device}-${activity.toLowerCase().replaceAll(' ','-')}.png`),fullPage:device==='desktop'});
        if(device==='mobile'&&activity==='Main Groups')await page.locator('.result-record').first().screenshot({path:path.join(output,'mobile-participant-record.png')});
        if(device==='mobile'&&activity==='My Reflections')await page.locator('.reflection-table tbody tr').first().screenshot({path:path.join(output,'mobile-appointment-record.png')});
        if(device==='mobile'&&activity==='Hotel Rooms')await page.locator('.hotel-room').first().screenshot({path:path.join(output,'mobile-room-card.png')});
      }
      console.log(`Passed all six tabs at ${width}px`);
    }
    await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Main Groups',exact:true}).click();
    await page.getByRole('button',{name:'Edit Teams',exact:true}).click();
    const first=generated.activities.find(a=>a.activity_id==='main').groups[0].participant_ids.slice(0,2);
    await page.getByRole('combobox',{name:'First participant to switch',exact:true}).selectOption(first[0]);
    await page.getByRole('combobox',{name:'Second participant to switch',exact:true}).selectOption(first[1]);
    assert.equal(await page.locator('.result-record.is-selected').count(),2,'Swap selection has a separate visible state');
    assert.ok(await page.getByRole('button',{name:'Undo Last Change',exact:true}).isDisabled());
    await page.screenshot({path:path.join(output,'desktop-selected-edit-state.png'),fullPage:true});
    await page.getByRole('button',{name:'Cancel Changes',exact:true}).click();
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.results-tab').first().evaluate(e=>getComputedStyle(e).transitionDuration),'0s');
    await page.locator('.results-tab').first().focus();await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineWidth),'2px','Keyboard focus is visible');
    const savedRequest=page.waitForRequest(request=>request.url().endsWith('/api/export/editable'));
    const[download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Editable Excel',exact:true}).click()]);
    assert.deepEqual((await savedRequest).postDataJSON().allocation,generated,'Navigation, resizing, and cancelled edits preserve assignments');
    await download.saveAs(path.join(output,download.suggestedFilename()));assert.equal(await download.failure(),null);
    assert.equal(optimizations,1,'Presentation never regenerates activities');assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(output,'observations.json'),JSON.stringify(observations,null,2));
    console.log(JSON.stringify({passed:true,participants:27,businessChemistry:true,responsiveViews:18,unchangedAssignments:true,artifacts:output},null,2));
  }catch(error){await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(output,'failure.txt'),await page.locator('body').innerText()).catch(()=>{});console.error(`Design review failure artifacts: ${output}`);throw error;}
  finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
