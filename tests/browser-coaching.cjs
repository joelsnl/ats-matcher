/* Run against --mode basic. Real coaching APIs; isolated browser + fictional CV. */
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process');
(async()=>{
  const profile=fs.mkdtempSync(path.join(os.tmpdir(),'ats-coaching-check-'));
  const child=spawn(process.env.CHROME_PATH||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));let ws;const checks=[];
  const watchdog=setTimeout(()=>{console.error('FAIL Browser checks timed out');child.kill();process.exit(1);},90000);
  try{
    let port;for(let i=0;i<100;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{}await sleep(100);}if(!port)throw Error('Browser did not start');
    const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
    let seq=0;const pending=new Map(),errors=[];
    ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.method==='Runtime.exceptionThrown')errors.push(d.params.exceptionDetails);if(d.id){const p=pending.get(d.id);pending.delete(d.id);d.error?p.reject(Error(d.error.message)):p.resolve(d.result);}};
    const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
    const ev=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
    const check=async(expression,label)=>{if(!await ev(expression))throw Error(label);checks.push(label);console.log('PASS',label);};
    const until=async expression=>{for(let i=0;i<100;i++){if(await ev(expression))return;await sleep(50);}throw Error('Timed out waiting for '+expression);};
    const click=async selector=>{await ev(`document.querySelector(${JSON.stringify(selector)}).click()`);await sleep(30);};
    const fill=async(selector,value)=>ev(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    const shot=async name=>{const r=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(profile,name+'.png'),Buffer.from(r.data,'base64'));};
    await call('Runtime.enable');await call('Page.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await call('Page.navigate',{url:process.argv[2]||'http://127.0.0.1:8881'});await until("typeof Coaching!=='undefined'&&typeof state!=='undefined'&&parseMode==='basic'");
    await ev(`state.profile.name='Taylor';state.profile.skills=['Python','Jenkins'];state.profile.roles=['Engineer'];state.profile.background.achievements='I wrote Python validation checks. I explained the results to stakeholders.';state.jobs=[JobStore.normalize({source:'fixture',job_id:'one',title:'Platform Engineer',company:'Example Studio',application_url:'https://example.com/role',description:'Requirements:\\nPython, CI/CD and Kubernetes.\\nCommunication with stakeholders.\\nNice to have:\\nTerraform and AWS.'})];state.shortlist.ids=['fixture:one'];ensureSaved('fixture:one');save();navigate('practice');`);
    // Use actual newlines in the description, not a literal slash-n fixture.
    await ev("state.jobs[0].description=state.jobs[0].description.replaceAll('\\\\n','\\n');persist();");
    await check("document.querySelector('.practice-role').textContent.includes('Platform Engineer')",'Practice starts with the user’s saved role');
    await click('.practice-role [data-action=interview-prep]');await until("!!document.querySelector('.lesson-card')");
    await check("state.applications['fixture:one'].interviewPrep.learning_plan.lessons.some(l=>l.skill==='Kubernetes'&&l.mode==='foundation')&&state.applications['fixture:one'].interviewPrep.learning_plan.lessons.some(l=>l.skill==='Python'&&l.mode==='refresher')&&state.applications['fixture:one'].interviewPrep.learning_plan.lessons.some(l=>l.kind==='soft')",'Real API produces foundations, refreshers and people-skill rehearsals');
    await check("document.querySelectorAll('.lesson-card').length<=7",'The learning queue remains focused');
    await shot('role-plan-desktop');
    const skill=await ev("state.applications['fixture:one'].interviewPrep.learning_plan.lessons.find(l=>l.skill==='Kubernetes').id");
    await click(`[data-action=coaching-lesson][data-skill="${skill}"]`);
    await fill('[data-practice-field=warmup]','A deployment maintains the desired replicas.');
    await fill('[data-practice-field=answer]','I would compare the Service selector with the Pod labels, then inspect readiness and endpoints.');
    await fill('[data-practice-field=reflection]','I need to distinguish container startup from readiness.');
    await click('[data-practice-check="0"]');await click('[data-action=coaching-complete]');
    await check(`!!state.applications['fixture:one'].practiceProgress['${skill}'].completedAt&&!!state.applications['fixture:one'].practiceProgress['${skill}'].reviewOn`,'An attempted session saves completion and a next-day review date');
    await call('Page.reload');await until("typeof state!=='undefined'&&!!document.querySelector('h1')");
    await ev("showInterviewPrep('fixture:one')");await click(`[data-action=coaching-lesson][data-skill="${skill}"]`);
    await check("document.querySelector('[data-practice-field=answer]').value.includes('selector')&&document.querySelector('[data-practice-check]').checked",'Answers, self-checks and plan survive a reload');
    await check("state.profile.skills.join(',')==='Python,Jenkins'",'Finishing practice does not add skills to the CV');
    await click('[data-action=coaching-adapt]');await until("!!document.querySelector('.lesson-work')");
    await check("document.querySelector('#modal').textContent.includes('Refresh what I know')",'A learner can switch an unevidenced skill to a refresher');
    await check(`state.applications['fixture:one'].practiceProgress['${skill}'].history.length===1&&document.querySelector('[data-practice-field=answer]').value===''`,'A changed exercise archives the previous attempt and clears its self-checks');
    await fill('[data-practice-field=answer]','I would compare the labels and selectors before checking readiness.');
    await ev(`window.feedbackFetch=window.fetch;window.fetch=async(url,options)=>url==='/api/practice-feedback'?new Response(JSON.stringify({generated:true,observations:[{criterion:'The selector matches the labels.',status:'partial',evidence:'compare the labels and selectors',comment:'You have named the comparison.',next_step:'Show one concrete pair of labels.'}],follow_up:'What would a mismatch look like?',note:'Coaching suggestion.'}),{status:200}):window.feedbackFetch(url,options);parseMode='local-model';document.querySelector('[data-action=coaching-feedback]').disabled=false;`);
    await click('[data-action=coaching-feedback]');await until("!!document.querySelector('.practice-feedback')");
    await check("document.querySelector('.practice-feedback blockquote').textContent==='compare the labels and selectors'",'Model feedback displays its supporting quotation and an actionable next step');
    await fill('[data-practice-field=answer]','I changed my answer and now describe the exact labels.');
    await check(`!document.querySelector('.practice-feedback')&&!state.applications['fixture:one'].practiceProgress['${skill}'].feedback`,'Editing an answer clears feedback for the older attempt');
    await ev("window.fetch=window.feedbackFetch;parseMode='basic';closeModal();showReview('fixture:one')");
    await until("document.getElementById('role-evidence').textContent.includes('Evidence found in your CV')");
    await check("document.getElementById('role-evidence').textContent.includes('I wrote Python validation checks.')&&document.getElementById('role-evidence').textContent.includes('Communication')",'Comparison uses the same CV evidence and people-skill topics as the plan');
    await ev("closeModal();showCoverLetter('fixture:one')");
    await fill('#cover-letter-text','I ran production AWS systems for 42 years. I also wrote Python checks for import files and explained results to stakeholders. This work connects to the validation and collaboration described in the listing.\n\nTaylor');
    await ev("document.getElementById('letter-tone').value='warm';document.getElementById('letter-tone').dispatchEvent(new Event('change',{bubbles:true}))");
    await click('[data-action=coaching-check-letter]');await until("!!document.querySelector('.letter-review')");
    await check("document.querySelector('.letter-review').textContent.includes('AWS')&&document.querySelector('.letter-review').textContent.includes('42')",'Manual drafts can be checked for unsupported tools and numbers without AI');
    await shot('letter-review-desktop');
    await fill('#cover-letter-text','A revised draft that I have not saved as a version yet.');
    await call('Page.reload');await until("typeof state!=='undefined'&&!!document.querySelector('h1')");await ev("showCoverLetter('fixture:one')");
    await check("document.getElementById('cover-letter-text').value.includes('revised draft')&&document.getElementById('letter-tone').value==='warm'",'Unsaved letter drafts and writing preferences survive reload');
    await fill('#cover-letter-text','');await ev("closeModal();showCoverLetter('fixture:one')");
    await check("document.getElementById('cover-letter-text').value===''",'Intentionally clearing a draft does not restore an old saved letter');
    await fill('#cover-letter-text','Keep this edited letter during an unsuccessful generation.');
    await ev("window.actualFetch=window.fetch;parseMode='local-model';window.fetch=async(url,options)=>url==='/api/cover-letter'?new Response(JSON.stringify({error:'Model unavailable'}),{status:502}):window.actualFetch(url,options);Coaching.generateLetter('fixture:one')");
    await until("!!document.getElementById('cover-letter-text')");
    await check("document.getElementById('cover-letter-text').value.includes('Keep this edited')&&state.versions.some(v=>v.body.includes('Keep this edited'))",'Failed regeneration preserves and versions the edited letter');
    await ev("window.fetch=window.actualFetch;parseMode='basic';closeModal();state.profile.skills.push('Docker');showInterviewPrep('fixture:one')");
    await check("document.getElementById('modal').textContent.includes('has changed')",'Changed profile evidence is clearly marked on an older plan');
    for(const theme of ['light','dark']){
      await ev(`applyTheme('${theme}')`);await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
      for(const view of ['plan','lesson','letter']){
        await ev(view==='plan'?"showInterviewPrep('fixture:one')":view==='lesson'?`Coaching.cancel();document.querySelector('[data-action=coaching-lesson][data-skill="${skill}"]').click()` : "showCoverLetter('fixture:one')");
        await check("document.documentElement.scrollWidth<=innerWidth&&document.getElementById('modal').scrollWidth<=document.getElementById('modal').clientWidth+1",`${theme} mobile ${view} fits without horizontal scrolling`);
        await shot(`${theme}-mobile-${view}`);
        if(view==='letter')await ev("closeModal();showInterviewPrep('fixture:one')");
      }
    }
    // Deliberately ignore AbortSignal: even a late response must not reopen a closed modal.
    await ev("closeModal();window.fetch=(url,options)=>url==='/api/interview-prep'?new Promise(resolve=>window.latePrep=resolve):window.actualFetch(url,options);void generateInterviewPrep('fixture:one');");
    await until("typeof window.latePrep==='function'");await ev("closeModal();window.latePrep(new Response(JSON.stringify({briefing:'Late response',resources:[],stories:[],ask_them:[]}))); ");await sleep(100);
    await check("!document.getElementById('modal').open&&state.applications['fixture:one'].interviewPrep.briefing!=='Late response'",'A late response cannot reopen a dismissed generation or replace saved work');
    // Unsafe strings remain text inside the lesson renderer.
    await ev(`window.fetch=window.actualFetch;const l=state.applications['fixture:one'].interviewPrep.learning_plan.lessons.find(l=>l.id==='${skill}');l.exercise='<img src=x onerror=alert(1)>';showInterviewPrep('fixture:one');`);
    await click(`[data-action=coaching-lesson][data-skill="${skill}"]`);
    await check("!document.querySelector('#modal img')&&document.querySelector('.practice-brief').textContent.includes('<img')",'Generated exercise text is escaped');
    if(errors.length)throw Error(JSON.stringify(errors));
    console.log(JSON.stringify({result:'PASS',checks,screenshots:profile}));
  }finally{clearTimeout(watchdog);if(ws)ws.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
