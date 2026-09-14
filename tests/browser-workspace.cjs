const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');const {pathToFileURL}=require('node:url');
(async()=>{
 const profile=fs.mkdtempSync(path.join(os.tmpdir(),'ats-app-check-'));
 const child=spawn(process.env.CHROME_PATH||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
 let ws;const checks=[];const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 try{
  let port;for(let i=0;i<100;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{}await sleep(100);}if(!port)throw Error('Browser did not start');
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let seq=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.method==='Runtime.exceptionThrown')errors.push(d.params.exceptionDetails);if(d.id){const p=pending.get(d.id);pending.delete(d.id);d.error?p.reject(Error(d.error.message)):p.resolve(d.result);}};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const ev=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const check=async(expression,label)=>{if(!await ev(expression))throw Error(label);checks.push(label);};
  const click=async selector=>{await ev(`document.querySelector(${JSON.stringify(selector)}).click()`);await sleep(35);};
  const fill=async(selector,value)=>{await ev(`document.querySelector(${JSON.stringify(selector)}).value=${JSON.stringify(value)};document.querySelector(${JSON.stringify(selector)}).dispatchEvent(new Event('input',{bubbles:true}))`);};
  const shot=async name=>{const r=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(profile,name+'.png'),Buffer.from(r.data,'base64'));};
  await call('Runtime.enable');await call('Page.enable');await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  const url=process.argv[2]||'http://127.0.0.1:8766';
  await call('Page.navigate',{url});for(let i=0;i<50;i++){if(await ev("!!document.querySelector('h1')"))break;await sleep(100);}


  await check("document.querySelectorAll('.job-card').length===0 && document.querySelector('h1').textContent.includes('there')",'Fresh workspace has no fictional jobs or seeded personal profile');
  const installMock=async()=>ev(`window.realFetch=window.fetch;window.batch=1;window.mockError=false;window.mockPartial=false;window.searchCalls=0;window.fetch=async (url,options)=>{
    if(String(url).includes('/api/interview-prep'))return new Response(JSON.stringify({briefing:'This listing will spend time on React and SQL work you already do.',stories:[{prompt:'Walk through a reporting trade-off.',anchor:'Example Co'}],ask_them:['What does a useful first month look like?'],resources:[{title:'Tech Interview Handbook',url:'https://www.techinterviewhandbook.org/',blurb:'Open coding paths.',topics:['coding']},{title:'Behavioral interview guide',url:'https://www.techinterviewhandbook.org/behavioral-interview/',blurb:'Free behavioral patterns.',topics:['behavioral']}],generated:false}),{status:200,headers:{'Content-Type':'application/json'}});
    if(url!=='/api/jobs')return window.realFetch(url,options);
    window.searchCalls++;window.lastQuery=JSON.parse(options.body);
    const raw=window.batch===1?[
      {source:'linkedin',job_id:'100',title:'Frontend Engineer',company:'Real Source Example',location:'Berlin',application_url:'https://www.linkedin.com/jobs/view/100',posted_relative:'1 hour ago'},
      {source:'linkedin',job_id:'200',title:'Remote Developer',company:'Second Example',location:'Germany',workplace_type:'remote',application_url:'https://www.linkedin.com/jobs/view/200'}
    ]:window.batch===2?[
      {source:'linkedin',job_id:'300',title:'Backend Engineer',company:'Third Example',location:'Berlin',application_url:'https://www.linkedin.com/jobs/view/300'}
    ]:window.batch===3?[
      {source:'linkedin',job_id:'400',title:'<img src=x onerror=alert(1)>',company:'<b>Untrusted</b>',location:'<script>bad</script>',application_url:'https://www.linkedin.com/jobs/view/400'},
      {source:'linkedin',job_id:'500',title:'Unsafe',company:'Unsafe',application_url:'javascript:alert(1)'}
    ]:[];
    return new Response(JSON.stringify({jobs:window.mockError?[]:raw,jobs_meta:{status:window.mockError?'error':window.mockPartial?'partial':'ok',providers:[{provider:'linkedin',next_page:1}],errors:window.mockError?['Source rate limited. Try again later.']:[],warnings:window.mockPartial?['Some source pages were unavailable.']:[]}}),{status:window.mockError?502:200,headers:{'Content-Type':'application/json'}});
  }`);
  await installMock();
  await click('[data-nav="live"]');await fill('[name=keywords]','engineer');await fill('[name=location]','Berlin');
  await ev("document.getElementById('live-search-form').requestSubmit()");await sleep(80);
  await check("document.querySelectorAll('#live-results .job-card').length===2",'Search results render shared saveable job cards');
  await click('[data-action="save-job"][data-id="linkedin:100"]');
  await check("document.getElementById('saved-count').textContent==='1'",'Saving from search updates the application count');
  await click('[data-nav="today"]');
  await check("document.querySelectorAll('#job-results .job-card').length===2 && !document.getElementById('job-results').textContent.includes('Full-time') && !document.getElementById('job-results').textContent.includes('shared skill')",'Daily shortlist uses real results without invented job type or skills');
  await click('[data-action="job"][data-id="linkedin:100"]');
  await check("document.querySelector('#modal a').href==='https://www.linkedin.com/jobs/view/100' && document.getElementById('modal').textContent.includes('Open original listing') && document.querySelector('#modal [data-action=cover-letter]') && document.querySelector('#modal [data-action=interview-prep]') && !document.getElementById('modal').textContent.includes('Salary not listed') && !document.getElementById('modal').textContent.includes('Work arrangement not listed')",'Job details expose the real source without inventing missing listing details');
  await click('#modal [data-action="review"]');await fill('[name=description]','We need React, SQL, and Python experience.');await ev("document.getElementById('description-form').requestSubmit()");
  await check("document.querySelectorAll('.review-box').length===2 && !document.querySelector('[data-action=reward]')",'Pasted requirements provide a free actual keyword comparison');
  await ev("state.profile.name='Taylor'");await click('[data-action="close-modal"]');await click('[data-action="job"][data-id="linkedin:100"]');await click('#modal [data-action=interview-prep]');await sleep(200);
  await check("document.getElementById('modal').textContent.includes('Open practice materials') && !!document.querySelector('#modal a[href*=\"techinterviewhandbook\"]') && document.getElementById('modal').textContent.includes('Stories from your work')",'Interview prep lists open materials and story prompts for the listing');
  await click('[data-action="close-modal"]');await click('[data-nav="applications"]');
  await click('[data-action="workspace"][data-id="linkedin:100"]');await fill('[name=note]','Ask about the team and accessibility.');await fill('[name=followup]','2026-10-01');await fill('[name=status]','Applied');await ev("document.getElementById('workspace-form').requestSubmit()");
  await check("state.applications['linkedin:100'].status==='Applied' && state.applications['linkedin:100'].note.includes('accessibility')",'Application stage, notes, and next-step date save');
  await click('[data-action="workspace"][data-id="linkedin:100"]');await click('[data-action="draft"]');await fill('[name=body]','My actual project experience.');await ev("document.getElementById('draft-form').requestSubmit()");
  await check("state.versions.length===1 && !!document.querySelector('[data-action=download-version]') && !document.querySelector('[data-action=pro]')",'Real applications support saved and downloadable drafts');await click('[data-action="close-modal"]');
  await call('Page.reload');await sleep(200);await installMock();
  await check("state.applications['linkedin:100'].note.includes('accessibility') && state.versions.length===1 && jobById('linkedin:100').description.includes('React') && state.applications['linkedin:100'].interviewPrep.resources.length>0",'Listing, description, notes, status, draft, and interview prep survive reload');
  await click('[data-nav="live"]');await ev("window.batch=2;document.getElementById('live-search-form').requestSubmit()");await sleep(100);
  await click('[data-nav="today"]');
  await check("document.querySelectorAll('#job-results .job-card').length===1 && !!document.querySelector('[data-job-card=\"linkedin:300\"]') && !!state.applications['linkedin:100'] && !!jobById('linkedin:100')",'A new search replaces the shortlist and retains saved applications');
  await ev("window.mockError=true");await click('[data-action="refresh-jobs"]');await sleep(100);
  await check("document.getElementById('shortlist-status').textContent.includes('Showing your previous results') && !!document.querySelector('[data-job-card=\"linkedin:300\"]')",'Failed refresh keeps previous results and explains the failure');
  await ev("window.mockError=false;window.mockPartial=true");await click('[data-action="refresh-jobs"]');await sleep(100);
  await check("document.getElementById('shortlist-status').textContent.includes('Some source pages')",'Partial searches preserve visible source warnings');
  await click('[data-action="dismiss"][data-id="linkedin:300"]');await ev("document.getElementById('dismiss-form').requestSubmit()");await check("!document.querySelector('[data-job-card=\"linkedin:300\"]')",'Pass hides a real listing');await click('#toast button');
  await check("!!document.querySelector('[data-job-card=\"linkedin:300\"]')",'Undo restores the passed listing');
  await shot('real-shortlist-desktop');
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(const view of ['today','applications','live','profile']){await click('[data-nav="'+view+'"]');await check("document.documentElement.scrollWidth<=innerWidth",'Mobile '+view+' has no horizontal overflow');}await shot('real-profile-mobile');
  await fill('[name=name]','Taylor');await fill('[name=roles]','Data analyst');await fill('[name=location]','Hamburg');await ev("document.getElementById('profile-form').requestSubmit()");await click('[data-nav="live"]');
  await check("document.querySelector('[name=keywords]').value==='Data analyst' && document.querySelector('[name=location]').value==='Hamburg'",'Edited profile supplies new search defaults');
  await ev("window.batch=3;window.mockPartial=false;document.getElementById('live-search-form').requestSubmit()");await sleep(80);
  await check("!document.querySelector('#live-results img, #live-results script, #live-results b') && !jobById('linkedin:500')",'Untrusted source text is escaped and unsafe listing URLs are rejected');
  await click('[data-action="save-job"][data-id="linkedin:400"]');await click('[data-nav="applications"]');await click('[data-action="workspace"][data-id="linkedin:400"]');
  await check("!document.querySelector('#modal img, #modal script, #modal b')",'Untrusted source text stays safe in the application workspace');await click('[data-action="close-modal"]');
  await click('[data-nav="live"]');await ev("window.batch=4;document.getElementById('live-search-form').requestSubmit()");await sleep(80);await click('[data-nav="today"]');
  await check("state.shortlist.ids.length===0 && state.applications['linkedin:100'] && !document.querySelector('#job-results .job-card')",'Successful empty searches clear the shortlist without deleting applications');
  await ev("window.realFetch=window.fetch;window.fetch=()=>new Promise(resolve=>window.resolveLate=resolve)");await click('[data-action="refresh-jobs"]');
  await click('[data-nav="profile"]');await click('[data-action="reset"]');await click('[data-action="confirm-reset"]');
  await ev("window.resolveLate(new Response(JSON.stringify({jobs:[{source:'linkedin',job_id:'999',title:'Late result',company:'Example',application_url:'https://www.linkedin.com/jobs/view/999'}],jobs_meta:{status:'ok',errors:[],warnings:[],providers:[]}}),{headers:{'Content-Type':'application/json'}}))");await sleep(80);
  await check("state.jobs.length===0 && state.shortlist.ids.length===0",'A result arriving after reset cannot refill the cleared workspace');
  await ev("localStorage.setItem('ats-matcher-prototype-v1',JSON.stringify({version:1,sample:false,profile:{name:'Previous Person',roles:['Engineer'],skills:['React'],location:'Berlin',mode:'Any',goal:5},applications:{fern:{status:'Applied',note:'Keep this old note'}},versions:[{id:'old-draft',job:'fern',body:'Keep this old draft'}]}))");
  await call('Page.reload');await sleep(200);await click('[data-nav="profile"]');
  await check("state.profile.name==='Previous Person' && Object.keys(state.applications).length===0 && state.legacyWorkspace.applications.fern.note==='Keep this old note' && state.legacyWorkspace.versions[0].body==='Keep this old draft' && !!document.querySelector('[data-action=export-legacy]') && !document.body.textContent.includes('Sponsored') && !document.body.textContent.includes('Alex Morgan')",'Migration archives old notes and drafts while keeping the personal profile');
  if(errors.length)throw Error('Browser errors: '+JSON.stringify(errors));checks.push('No browser script errors');
  console.log(JSON.stringify({result:'PASS',url,checks,screenshots:profile}));
 }finally{if(ws)ws.close();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
