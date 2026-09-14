'use strict';

// Historical localStorage key. v1 demo listings are not loaded; notes and drafts stay exportable.
const EXERCISES = [
  {id:'story',icon:'✧',topic:'For every role',title:'Tell your story clearly',minutes:5,description:'Turn a real achievement into an interview answer that feels like you.',question:'Tell me about a time you solved a difficult problem at work.',answer:'Set the scene in one sentence. Explain what you needed to achieve, describe the actions you personally took, and finish with the outcome. Use a real example; include a number only if you can support it.',prompt:'Situation → your task → your actions → the result. What would you do differently next time?'},
  {id:'sql',icon:'⌘',topic:'Data & engineering',title:'A little SQL confidence',minutes:5,description:'Practice a realistic data question, then compare your approach with a worked answer.',question:'You have an orders table with customer_id and amount. How would you find customers whose total spending is more than €500?',answer:'Group the orders by customer, add up each customer’s spending, and use HAVING to filter the grouped totals.',code:'SELECT customer_id, SUM(amount) AS total_spent\nFROM orders\nGROUP BY customer_id\nHAVING SUM(amount) > 500;',prompt:'Explain why HAVING is used here instead of WHERE.'},
  {id:'question',icon:'↗',topic:'For every role',title:'Ask a better question',minutes:3,description:'End an interview with a question that helps you decide whether the role fits.',question:'The interviewer asks: “What would you like to know about working here?” What would you ask?',answer:'Try: “What would a successful first three months look like in this role?” It helps you understand expectations. Follow up with a question about how the team supports someone getting started.',prompt:'Write a question about something you genuinely need to know, such as expectations, team support, or how decisions are made.'}
];
const KEY = 'ats-matcher-prototype-v1';
const THEME_KEY = 'ats-matcher-theme';
const STATUSES = ['Saved','Applied','Interview','Closed'];
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text = (value, max=500) => typeof value === 'string' ? value.slice(0,max) : '';
const strings = value => Array.isArray(value) ? value.filter(v=>typeof v==='string').map(v=>v.trim().slice(0,80)).filter(Boolean).slice(0,40) : [];
const split = value => [...new Set(String(value).split(/[,;\n]/).map(v=>v.trim()).filter(Boolean))].slice(0,40);
function emptyBackground(){return {yearsExperience:null,recentTitles:[],employers:[],certifications:[],industry:'',cvText:'',achievements:''};}
function emptyApplication(){return {status:'Saved',note:'',followup:'',updated:today,coverLetter:'',interviewPrep:null,...Coaching.applicationFields({})};}
function readPrep(raw){
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return null;
  const resources=Array.isArray(raw.resources)?raw.resources.slice(0,10).map(item=>{
    if(!item||typeof item!=='object')return null;
    const title=text(item.title,120),url=JobStore.safeUrl(item.url);
    if(!title||!url)return null;
    const topics=Array.isArray(item.topics)?strings(item.topics).slice(0,6):split(item.topics).slice(0,6);
    return {title,url,blurb:text(item.blurb,280),topics};
  }).filter(Boolean):[];
  const stories=Array.isArray(raw.stories)?raw.stories.slice(0,6).map(item=>{
    if(!item||typeof item!=='object')return null;
    const prompt=text(item.prompt,400);
    return prompt?{prompt,anchor:text(item.anchor,200)}:null;
  }).filter(Boolean):[];
  const ask=(Array.isArray(raw.ask_them)?raw.ask_them:[]).map(item=>text(String(item||''),240)).filter(Boolean).slice(0,8);
  const briefing=text(raw.briefing,1200);
  if(!briefing&&!resources.length&&!stories.length)return null;
  return {briefing,stories,ask_them:ask,resources,generated:raw.generated===true,context:Coaching.readContext(raw.context),learning_plan:Coaching.readPlan(raw.learning_plan),generation_note:text(raw.generation_note,400)};
}
function readBackground(raw){
  const src=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw:{};
  const employers=Array.isArray(src.employers)?src.employers.map(item=>{
    if(typeof item==='string'){const name=text(item,120);return name?{name}:null;}
    if(!item||typeof item!=='object')return null;
    const name=text(item.name,120);if(!name)return null;
    const client=text(item.client,120);
    return client?{name,client}:{name};
  }).filter(Boolean).slice(0,15):[];
  const rawYears=src.years_experience??src.yearsExperience;const years=rawYears===null||rawYears===undefined||rawYears===''?NaN:Number(rawYears);
  return {yearsExperience:Number.isFinite(years)?Math.max(0,Math.min(60,years)):null,recentTitles:strings(src.recent_titles||src.recentTitles).slice(0,8),employers,certifications:strings(src.certifications).slice(0,15),industry:text(src.primary_industry||src.industry,80),cvText:text(src.cv_text||src.cvText,12000),achievements:text(src.achievements,3000)};
}
const localDay = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
const today = localDay();
const jobById = id => JobStore.present(state.jobs.find(j=>j.id===id));
const initialProfile = {name:'',skills:[],roles:[],location:'',mode:'Any',goal:5,reminder:false,reminderTime:'09:00',jobLanguage:'en',background:emptyBackground()};
const JOB_LANGUAGES=[['en','English'],['nl','Dutch'],['de','German'],['fr','French'],['es','Spanish'],['it','Italian'],['pt','Portuguese'],['pl','Polish'],['sv','Swedish'],['da','Danish'],['no','Norwegian'],['fi','Finnish'],['cs','Czech'],['hu','Hungarian'],['ro','Romanian'],['el','Greek'],['tr','Turkish'],['ru','Russian'],['uk','Ukrainian'],['ar','Arabic'],['he','Hebrew'],['hi','Hindi'],['ja','Japanese'],['ko','Korean'],['zh-CN','Chinese (Simplified)'],['zh-TW','Chinese (Traditional)'],['id','Indonesian'],['vi','Vietnamese'],['th','Thai']];
let jobLanguages=JOB_LANGUAGES;
function freshState(){return {version:2,sample:false,profile:{...initialProfile,skills:[],roles:[],background:emptyBackground()},jobs:[],shortlist:{ids:[],query:null,checkedAt:null,warnings:[]},legacyWorkspace:null,applications:{},dismissed:{},completed:[],answers:{},actions:[],tasks:{},versions:[]};}
function loadState(){
  try{return readWorkspace(JSON.parse(localStorage.getItem(KEY)));}catch{return freshState();}
}
function readWorkspace(raw){
  try {
    if (!raw || ![1,2].includes(raw.version) || !raw.profile) return freshState();
    if(raw.version===1){
      raw={...freshState(),profile:raw.sample===false?raw.profile:initialProfile,legacyWorkspace:{...raw}};
    }
    const s=freshState(),p=raw.profile;
    s.legacyWorkspace=raw.legacyWorkspace&&typeof raw.legacyWorkspace==='object'?raw.legacyWorkspace:null;
    s.profile={name:text(p.name,80),skills:strings(p.skills),roles:strings(p.roles).slice(0,8),location:text(p.location,100),mode:['Any','Remote','Hybrid','On-site'].includes(p.mode)?p.mode:'Any',goal:Math.min(20,Math.max(1,Number(p.goal)||5)),reminder:p.reminder===true,reminderTime:/^\d{2}:\d{2}$/.test(p.reminderTime)?p.reminderTime:'09:00',jobLanguage:JOB_LANGUAGES.some(([id])=>id===p.jobLanguage)?p.jobLanguage:'en',background:readBackground(p.background||{})};
    s.jobs=Array.isArray(raw.jobs)?[...new Map(raw.jobs.map(JobStore.normalize).filter(Boolean).map(j=>[j.id,j])).values()]:[];
    const ids=new Set(s.jobs.map(j=>j.id));
    for(const j of s.jobs){
      const a=raw.applications?.[j.id];
      if(a&&STATUSES.includes(a.status))s.applications[j.id]={status:a.status,note:text(a.note,5000),followup:/^\d{4}-\d{2}-\d{2}$/.test(a.followup)?a.followup:'',updated:text(a.updated,30),coverLetter:text(a.coverLetter,8000),interviewPrep:readPrep(a.interviewPrep),...Coaching.applicationFields(a)};
      if(typeof raw.dismissed?.[j.id]==='string')s.dismissed[j.id]=text(raw.dismissed[j.id],100);
    }
    if(raw.shortlist&&typeof raw.shortlist==='object')s.shortlist={ids:Array.isArray(raw.shortlist.ids)?[...new Set(raw.shortlist.ids.filter(id=>ids.has(id)))].slice(-500):[],query:raw.shortlist.query&&typeof raw.shortlist.query==='object'?raw.shortlist.query:null,checkedAt:text(raw.shortlist.checkedAt,50)||null,warnings:strings(raw.shortlist.warnings)};
    s.completed=strings(raw.completed).filter(id=>EXERCISES.some(e=>e.id===id));
    for(const e of EXERCISES)s.answers[e.id]=text(raw.answers?.[e.id],5000);
    s.actions=Array.isArray(raw.actions)?raw.actions.filter(a=>a&&/^\d{4}-\d{2}-\d{2}$/.test(a.day)&&typeof a.id==='string').map(a=>({day:a.day,id:text(a.id,400)})).slice(-500):[];
    if(raw.tasks&&typeof raw.tasks==='object')for(const [key,value] of Object.entries(raw.tasks).slice(-100))if(/^\d{4}-\d{2}-\d{2}:\w+$/.test(key))s.tasks[key]=value===true;
    s.versions=Array.isArray(raw.versions)?raw.versions.filter(v=>v&&ids.has(v.job)).map(v=>({id:text(v.id,80),job:v.job,title:text(v.title,100),body:text(v.body,20000),date:text(v.date,30)})).slice(-30):[];
    return s;
  }catch{return freshState();}
}
let state = loadState();
let currentView = 'today', activeFilter='All', searchTerm='', toastTimer, importDraft=null, importText='', importEpoch=0;
const coverRefresh={},prepRefresh={};
const main = $('#main'), modal=$('#modal');
let shortlistLoading=false,shortlistError='',searchEpoch=0,parseMode='offline',parseDevice='',storageOk=true;
function serverAvailable(){return /^https?:$/.test(location.protocol);}
function storageCaption(){
  if(parseMode==='local-model')return parseDevice==='gpu'?'<i></i> Saved on this device · AI matching on GPU':'<i></i> Saved on this device · AI matching';
  if(parseMode==='basic')return '<i></i> Saved on this device · basic CV reading';
  if(parseMode==='unavailable')return '<i></i> Saved on this device · model not loaded';
  return '<i></i> Saved on this device';
}
async function loadServerStatus(){
  if(!serverAvailable()){parseMode='offline';parseDevice='';return;}
  try{
    const response=await fetch('/api/health');
    const data=await response.json();
    parseMode=data.mode==='local-model'?'local-model':data.mode==='basic'?'basic':'unavailable';
    parseDevice=data.device==='gpu'?'gpu':data.device==='cpu'?'cpu':'';
    if(Array.isArray(data.languages)&&data.languages.length)jobLanguages=data.languages.map(item=>[item.id,item.label]).filter(row=>row[0]&&row[1]);
  }catch{parseMode='offline';parseDevice='';}
  if($('#page-label'))renderChrome();
}
function persist(){
  try{localStorage.setItem(KEY,JSON.stringify(state));storageOk=true;$('.local-badge').innerHTML=storageCaption();}
  catch{storageOk=false;$('.local-badge').textContent='Changes last for this visit only';notify('Browser storage is full or unavailable. Export your workspace to keep it.');}
}
function preferredTheme(){
  try{const saved=localStorage.getItem(THEME_KEY);if(saved==='dark'||saved==='light')return saved;}catch{}
  return window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
}
function applyTheme(theme){
  document.documentElement.dataset.theme=theme;
  const meta=document.querySelector('meta[name="theme-color"]');
  if(meta)meta.content=theme==='dark'?'#191e20':'#f1efe8';
  const button=$('#theme-toggle');
  if(!button)return;
  const dark=theme==='dark';
  button.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');
  button.setAttribute('aria-pressed',String(dark));
  button.textContent=dark?'☀':'☾';
}
function toggleTheme(){
  const next=document.documentElement.dataset.theme==='dark'?'light':'dark';
  try{localStorage.setItem(THEME_KEY,next);}catch{}
  applyTheme(next);
}
function notify(message, undo){
  clearTimeout(toastTimer);const el=$('#toast');el.replaceChildren(document.createTextNode(message));
  if(undo){const b=document.createElement('button');b.type='button';b.textContent='Undo';b.addEventListener('click',()=>{undo();el.hidden=true;});el.append(b);}
  el.hidden=false;toastTimer=setTimeout(()=>{el.hidden=true;},undo?9000:4500);
}
function recordAction(id){if(!state.actions.some(a=>a.id===id && a.day===today))state.actions.push({id,day:today});state.actions=state.actions.slice(-500);}
function save(){persist();renderChrome();}
function overlap(job){return JobStore.overlap(job,state.profile.skills);}
function descriptionPreview(text){
  const clean=String(text||'').replace(/\s+/g,' ').trim();
  if(!clean)return '';
  return clean.length<=170?clean:clean.slice(0,170).replace(/\s+\S*$/,'')+'…';
}
function matchTags(shared,limit=4){
  const tags=shared.slice(0,limit).map(s=>`<span class="tag matched">${esc(s)}</span>`).join('');
  return tags+(shared.length>limit?`<span class="tag matched">+${shared.length-limit} more</span>`:'');
}
function applyTag(j){
  if(j.easy_apply===true)return '<span class="tag apply-easy">Easy Apply</span>';
  if(j.easy_apply===false)return '<span class="tag">Company website</span>';
  return '';
}
function listingLink(j){
  return sourceLink(j,j.easy_apply===true?'Easy Apply on LinkedIn ↗':'Open original listing ↗');
}
function companyApplyLink(j){
  const url=JobStore.safeUrl(j.external_apply_url);
  return url?`<a class="button small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Apply on company site ↗</a>`:'';
}
function sortedJobs(){
  const ids=activeFilter==='Saved'?Object.keys(state.applications):state.shortlist.ids;
  const order=new Map(ids.map((id,i)=>[id,i]));
  return ids.map(jobById).filter(j=>j&&!state.dismissed[j.id]&&(activeFilter==='All'||activeFilter==='Saved'||j.mode===activeFilter)&&`${esc(j.title)} ${esc(j.company)} ${esc(j.location)} ${j.skills.join(' ')}`.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a,b)=>{const diff=overlap(b).length-overlap(a).length;return diff||((order.get(a.id)||0)-(order.get(b.id)||0));});
}
function searchFromProfile(){
  const roles=state.profile.roles.slice(0,3);
  return {keywords:roles.length>1?roles.map(r=>`"${r.replaceAll('"','')}"`).join(' OR '):(roles[0]||''),location:state.profile.location,workplace_type:state.profile.mode==='Any'?null:state.profile.mode.toLowerCase().replace('-','_'),date_since_posted:'past_week',sort_by:'recent',limit:25,page:0,providers:['linkedin'],translate_to:state.profile.jobLanguage||'en'};
}
function receiveJobs(payload,query){
  if(payload.jobs_meta.status==='error')return false;
  const comparable=q=>JSON.stringify({...q,page:0});
  const append=Number(query.page)>0&&state.shortlist.query&&comparable(query)===comparable(state.shortlist.query);
  const previous=append?state.shortlist.ids:[];
  const merged=JobStore.merge(state.jobs,payload.jobs,[...Object.keys(state.applications),...previous]);
  if(payload.jobs.length&&!merged.ids.length){shortlistError='The source returned listings without usable details. Your previous shortlist is still here.';return false;}
  state.jobs=merged.jobs;
  state.shortlist={ids:[...new Set([...previous,...merged.ids])].slice(-500),query:{...query},checkedAt:new Date().toISOString(),warnings:[...(payload.jobs_meta.errors||[]),...(payload.jobs_meta.warnings||[])]};
  if(merged.ids.length<payload.jobs.length)state.shortlist.warnings.push('Some duplicate or incomplete listings were left out.');
  shortlistError='';save();return true;
}
async function refreshShortlist(useProfile=false){
  if(shortlistLoading)return;
  const query={...(!useProfile&&state.shortlist.query?state.shortlist.query:searchFromProfile()),page:0};
  if(!query.keywords?.trim()){navigate('live');notify('Enter a role to find your first real opportunities.');return;}
  const request=++searchEpoch;shortlistLoading=true;shortlistError='';if(currentView==='today')renderToday();
  try{
    if(!/^https?:$/.test(location.protocol))throw Error('Open the local app server to search for live jobs.');
    const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(query)});
    const payload=await response.json();
    if(request!==searchEpoch)return;
    if(!payload.jobs_meta)throw Error(payload.error||'The search could not complete. Please try again.');
    if(payload.jobs_meta.status==='error')throw Error((payload.jobs_meta.errors||[]).join(' ')||'The job source is unavailable.');
    receiveJobs(payload,query);
  }catch(e){if(request===searchEpoch)shortlistError=e.message;}
  finally{shortlistLoading=false;if(currentView==='today')renderToday();}
}
const bookmark = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3h10v14l-5-3-5 3z"/></svg>';
function logo(j){return `<span class="company-logo ${j.color}" aria-hidden="true">${esc(j.mark)}</span>`;}
function openModal(html,eyebrow='YOUR NEXT STEP'){
  Coaching.cancel();
  $('#modal-content').innerHTML=html;$('#modal-eyebrow').textContent=eyebrow;
  if(!modal.open)modal.showModal();modal.scrollTop=0;
}
function closeModal(){importEpoch++;Coaching.cancel();modal.close();}
function renderChrome(){
  document.body.dataset.view=currentView;
  const name=state.profile.name;
  $('#sidebar-name').textContent=name||'Your profile';
  $('#avatar').textContent=name.split(/\s+/).slice(0,2).map(v=>v[0]||'').join('').toUpperCase();
  $('#sidebar-plan').textContent='Local workspace';
  $('#saved-count').textContent=Object.keys(state.applications).length;
  document.querySelectorAll('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===currentView);if(a.dataset.nav===currentView)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  const activeTab=document.querySelector('[data-nav].active');
  if(activeTab){
    const tabs=activeTab.parentElement,tabBounds=activeTab.getBoundingClientRect(),tabsBounds=tabs.getBoundingClientRect();
    if(tabBounds.left<tabsBounds.left)tabs.scrollLeft+=tabBounds.left-tabsBounds.left;
    else if(tabBounds.right>tabsBounds.right)tabs.scrollLeft+=tabBounds.right-tabsBounds.right;
  }
  $('.app-footer span:last-child').textContent=parseMode==='local-model'?(parseDevice==='gpu'?'Live jobs · Local AI matching on GPU':'Live jobs · Local AI matching'):'Live jobs · Progress saved on this device';
  $('#page-label').textContent={today:'Daily shortlist',live:'Live job search',applications:'My applications',practice:'Interview practice',profile:'My profile'}[currentView];
  if(storageOk)$('.local-badge').innerHTML=storageCaption();
}
function heading(title,description,action=''){
  const sections={today:'01 / THE SHORTLIST',live:'02 / OPPORTUNITY SEARCH',applications:'03 / APPLICATION FILES',practice:'04 / THE REHEARSAL ROOM',profile:'05 / YOUR PERSONAL FILE'};
  return `<div class="page-heading"><div><div class="eyebrow">${sections[currentView]||'THE CAREER DESK'}</div><h1>${title}</h1><p>${description}</p></div>${action||`<span class="date-pill">${esc(new Date().toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'})).toUpperCase()}</span>`}</div>`;
}
function sourceLink(j,label='Open original listing ↗'){
  const url=JobStore.safeUrl(j.application_url);
  return url?`<a class="button secondary small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`:'';
}
function jobCard(j){
  const saved=!!state.applications[j.id],shared=overlap(j),preview=descriptionPreview(JobStore.displayedDescription(j));
  return `<article class="job-card" data-job-card="${esc(j.id)}"><div class="job-top">${logo(j)}<div class="job-heading"><h3><button data-action="job" data-id="${esc(j.id)}">${esc(j.title)}</button></h3><p>${esc(j.company)} · ${esc(j.location)}</p></div><button class="save-button ${saved?'saved':''}" data-action="save-job" data-id="${esc(j.id)}" aria-label="${saved?'Remove':'Save'} ${esc(j.title)}" aria-pressed="${saved}">${bookmark}</button></div><div class="job-tags"><span class="tag">${esc(j.source)}</span>${applyTag(j)}${j.workplace_type?`<span class="tag">${esc(j.mode)}</span>`:''}${j.employment?`<span class="tag">${esc(j.employment)}</span>`:''}${j.salary!=='Salary not listed'?`<span class="tag">${esc(j.salary)}</span>`:''}${j.posted?`<span class="tag">${esc(j.posted)}</span>`:''}${matchTags(shared)}</div>${preview?`<p class="job-snippet">${esc(preview)}</p>`:''}<div class="job-bottom"><span class="quiet">${shared.length?`${shared.length} covered skill${shared.length===1?'':'s'}`:j.description?'No covered skills yet':'Open the listing for full requirements'}</span><div class="job-actions">${JobStore.safeUrl(j.external_apply_url)?`<a class="text-button" href="${esc(JobStore.safeUrl(j.external_apply_url))}" target="_blank" rel="noopener noreferrer">Apply ↗</a>`:''}<button class="text-button quiet" data-action="dismiss" data-id="${esc(j.id)}">Pass</button><button class="text-button" data-action="cover-letter" data-id="${esc(j.id)}">Write a letter</button><button class="text-button" data-action="interview-prep" data-id="${esc(j.id)}">Prep interview</button><button class="text-button" data-action="job" data-id="${esc(j.id)}">Take a look ↗</button></div></div></article>`;
}
function weekData(){
  const monday=new Date();monday.setHours(0,0,0,0);monday.setDate(monday.getDate()-((monday.getDay()+6)%7));
  const start=localDay(monday),actions=state.actions.filter(a=>a.day>=start&&a.day<=today);
  return {monday,actions};
}
function dailyTask(id,label,description){const done=!!state.tasks[`${today}:${id}`];return `<div class="task-row ${done?'completed':''}"><button class="task-check ${done?'done':''}" data-action="task" data-id="${id}" aria-label="${done?'Mark incomplete':'Complete'}: ${label}" aria-pressed="${done}">${done?'✓':''}</button><div><strong>${label}</strong><p>${description}</p></div></div>`;}
function rightColumn(){
  const {monday,actions}=weekData();
  const days=Array.from({length:7},(_,i)=>{const d=new Date(monday);d.setDate(d.getDate()+i);const key=localDay(d);return `<div class="day ${actions.some(a=>a.day===key)?'active':''} ${key===today?'today':''}">${['M','T','W','T','F','S','S'][i]}<span>${actions.some(a=>a.day===key)?'✓':d.getDate()}</span></div>`;}).join('');
  const taskJob=Object.keys(state.applications).find(id=>state.applications[id].status==='Applied');
  return `<aside class="right-column" aria-label="Your progress and next steps"><section class="right-card"><div class="week-header"><h2>This week</h2><span>ACTIVITY</span></div><div class="weekdays" aria-label="Days with completed actions">${days}</div><div class="progress-track" role="progressbar" aria-label="Weekly action goal" aria-valuemin="0" aria-valuemax="${state.profile.goal}" aria-valuenow="${Math.min(actions.length,state.profile.goal)}"><span style="width:${Math.min(100,actions.length/state.profile.goal*100)}%"></span></div><div class="progress-caption"><strong>${actions.length} of ${state.profile.goal} actions</strong><button class="text-button" data-action="navigate" data-view="profile">Edit goal</button></div><p class="tiny-note">A saved role or a completed exercise counts toward your goal.</p></section><section class="right-card"><h2>On your agenda</h2>${dailyTask('shortlist','Explore your shortlist','Find one opportunity worth a closer look.')}${dailyTask('practice','Practice one answer','A few minutes can make a difference.')}${taskJob?`<div class="task-row"><span aria-hidden="true">↗</span><div><strong>Check in on ${esc(jobById(taskJob).company)}</strong><button class="text-button" data-action="workspace" data-id="${taskJob}">Open application →</button></div></div>`:dailyTask('reflect','Write down what matters','What would make your next role a good fit?')}</section><section class="right-card practice-teaser"><span class="eyebrow">DESK NOTE / PRACTICE</span><div class="practice-symbol" aria-hidden="true">↗</div><h2>Before the interview,<br>try it out here.</h2><p>Take five minutes to turn a real experience into an answer you can use.</p><button class="button" data-action="exercise" data-id="${state.profile.skills.some(s=>s.toLowerCase()==='sql')?'sql':'story'}">Try a practice question ↗</button></section></aside>`;
}
function renderJobList(){
  const jobs=sortedJobs();
  const note=shortlistLoading?'Checking the job source and reading public descriptions. Your saved applications stay available.':shortlistError;
  const context=state.shortlist.query?`Search: ${esc(state.shortlist.query.keywords)}${state.shortlist.query.location?' · '+esc(state.shortlist.query.location):''}. Last checked ${esc(new Date(state.shortlist.checkedAt).toLocaleString())}. Results may come from the source cache.`:'Search for a role to build your shortlist.';
  $('#shortlist-status').innerHTML=`${note?`<div class="notice ${shortlistError?'warning':''}" role="status">${esc(note)}${shortlistError&&state.shortlist.ids.length?' Showing your previous results.':''}</div>`:''}${state.shortlist.warnings.map(w=>`<div class="notice warning">${esc(w)}</div>`).join('')}<p class="subtle-caption">${context}</p>`;
  $('#job-results').innerHTML=jobs.length?jobs.map(jobCard).join(''):`<div class="empty-state"><div class="empty-icon">⌕</div><h3>${shortlistLoading?'Looking for opportunities…':shortlistError?'Search is unavailable right now.':state.shortlist.query?'No opportunities to show here.':'A blank page. Plenty of possibility.'}</h3><p>${state.shortlist.ids.length?'Try clearing your filters or searching for another role.':'Search by role and location. Save the jobs that interest you and track them in My applications.'}</p><button class="button secondary" data-action="navigate" data-view="live">Search jobs →</button>${activeFilter!=='All'||searchTerm?'<button class="text-button" data-action="clear-filters">Clear filters</button>':''}</div>`;
  $('#result-count').textContent=`${jobs.length} opportunit${jobs.length===1?'y':'ies'}`;
}
function renderToday(){
  const first=esc(state.profile.name.split(/\s+/)[0]||'there');
  main.innerHTML=heading(`Your next move, ${first}.`,'Real opportunities from your latest search, ordered by overlapping experience, including related tools.',`<div class="button-row"><button class="button secondary" data-action="navigate" data-view="live">Change search</button><button class="button" data-action="refresh-jobs" ${shortlistLoading?'disabled':''}>${shortlistLoading?'Searching…':'Refresh jobs ↻'}</button></div>`)+`<div class="dashboard-grid"><div class="main-column">${Desk.nextActions()}<section class="focus-card"><div><span class="eyebrow">A NOTE FOR YOUR SEARCH</span><h2>Find the role.<br>Make it your next move.</h2><p>Read the details. Compare what you bring. Keep the opportunities that deserve your time.</p><button class="text-button" data-action="focus-job">Find my next opportunity <span aria-hidden="true">→</span></button></div><div class="route-print" aria-label="Your process: explore, shortlist, apply"><div class="route-stop"><span>01</span><strong>Explore</strong></div><div class="route-stop"><span>02</span><strong>Shortlist</strong></div><div class="route-stop"><span>03</span><strong>Apply</strong></div></div></section><section aria-labelledby="shortlist-title"><div class="section-title"><h2 id="shortlist-title">Your latest opportunities</h2><small id="result-count"></small></div><div class="filter-bar" role="group" aria-label="Filter opportunities">${['All','Remote','Hybrid','On-site','Saved'].map(f=>`<button class="chip ${activeFilter===f?'selected':''}" data-action="filter" data-filter="${f}" aria-pressed="${activeFilter===f}">${f==='All'?'All opportunities':f}</button>`).join('')}<label class="filter-input"><span aria-hidden="true">⌕</span><input type="search" id="search-jobs" placeholder="Search roles" aria-label="Filter your shortlist" value="${esc(searchTerm)}"></label></div><div id="shortlist-status" aria-live="polite"></div><div class="job-list" id="job-results"></div><p class="subtle-caption">Roles with more overlapping experience appear first. Related tools count. A work arrangement or salary appears only when the listing supplies it. This is not a hiring score.</p></section></div>${rightColumn()}</div>`;
  renderJobList();
}
function renderApplications(){
  const apps=Object.entries(state.applications),applied=apps.filter(([,a])=>a.status==='Applied').length,interviews=apps.filter(([,a])=>a.status==='Interview').length;
  main.innerHTML=heading('Applications, in order.','Every saved role, follow-up, and conversation. Keep the whole search in view.',`<div class="button-row"><button class="button secondary" data-action="navigate" data-view="today">Find opportunities ↗</button><button class="button" data-action="desk-add-job">Add a listing link +</button></div>`)+`<div class="stats-row"><div class="stat"><strong>${apps.length}</strong><span>Opportunities tracked</span></div><div class="stat"><strong>${applied}</strong><span>Applications recorded</span></div><div class="stat"><strong>${interviews}</strong><span>Interview conversations</span></div></div>`+(apps.length?`<div class="board">${STATUSES.map(status=>`<section class="board-column"><div class="board-label">${status}<span>${apps.filter(([,a])=>a.status===status).length}</span></div>${apps.filter(([,a])=>a.status===status).map(([id,a])=>{const j=jobById(id);return `<article class="application-card">${logo(j)}<h3>${esc(j.title)}</h3><p>${esc(j.company)}${a.followup?`<br>Next step: ${esc(a.followup)}`:''}</p><label class="field"><span class="sr-label">Application stage</span><select data-status-job="${id}" aria-label="Stage for ${esc(j.title)}">${STATUSES.map(s=>`<option ${s===a.status?'selected':''}>${s}</option>`).join('')}</select></label><button class="text-button" data-action="workspace" data-id="${id}">Open workspace ↗</button></article>`;}).join('')||'<div class="board-empty">Room for your next step.</div>'}</section>`).join('')}</div>`:`<div class="empty-state"><div class="empty-icon">▤</div><h3>Your first application file starts here.</h3><p>Save an opportunity from your shortlist. It will be waiting here, with space for notes and next steps.</p><button class="button" data-action="navigate" data-view="today">Explore my shortlist →</button></div>`)+`<p class="subtle-caption">Moving a card records your progress here. This app never sends an application to an employer.</p>`;
}
function profileFields(p){return `<div class="form-grid"><label class="field">What should we call you?<input name="name" required maxlength="80" value="${esc(p.name)}" autocomplete="given-name"></label><label class="field">Where would you like to work?<input name="location" maxlength="100" value="${esc(p.location)}" placeholder="For example, Amsterdam, Netherlands"><small>City and country together help LinkedIn find the right area. Leave blank to search without a location filter.</small></label><label class="field full">Roles you’re interested in<input name="roles" maxlength="650" value="${esc(p.roles.join(', '))}" placeholder="Frontend Developer, Product Engineer"><small>Separate roles with commas. Suggestions are yours to change.</small></label><label class="field full">Skills you want to bring<textarea name="skills" maxlength="3000" rows="3" placeholder="React, SQL, project management">${esc(p.skills.join(', '))}</textarea><small>Only include skills you actually have. Separate them with commas.</small></label><label class="field">Your preferred setup<select name="mode">${['Any','Remote','Hybrid','On-site'].map(m=>`<option ${p.mode===m?'selected':''}>${m}</option>`).join('')}</select></label><label class="field">Show job descriptions in<select name="jobLanguage">${jobLanguages.map(([id,label])=>`<option value="${esc(id)}" ${p.jobLanguage===id?'selected':''}>${esc(label)}</option>`).join('')}</select><small>Non-English listings are translated with Google Translate. You can still switch language on a listing.</small></label><label class="field">Small steps to aim for each week<input type="number" name="goal" min="1" max="20" required value="${p.goal}"><small>Saving a role or finishing practice counts.</small></label></div>`;}
function renderProfile(){
  main.innerHTML=heading('The experience you bring.','Your skills, your work, and where you want to go next. Keep this file up to date.',`<button class="button secondary" data-action="onboard">Import a CV ↗</button>`)+`<div class="profile-grid"><form class="form-card" id="profile-form"><h2>Your particulars</h2><p class="section-intro">Your profile is saved in this browser. You can change it anytime.</p>${profileFields(state.profile)}<div class="divider"></div><h3>Evidence the writer can use</h3><p class="tiny-note">Your preferred roles and location above are search preferences. The writer uses the career facts and real examples below.</p><label class="field field-row">A few real examples<textarea name="achievements" maxlength="3000" rows="6" placeholder="For each example: what was the situation, what did you personally do, and what changed? Include tools and numbers only when you can support them.">${esc(state.profile.background?.achievements||'')}</textarea><small>Include people skills too: a disagreement you resolved, someone you taught, or a decision you explained. Do not paste the job's requirements as your achievements.</small></label>${Coaching.careerFields(state.profile.background)}<details class="evidence-panel"><summary>Review the CV text used for generation</summary><label class="field field-row">Your CV text<textarea name="cvText" maxlength="12000" rows="10">${esc(state.profile.background?.cvText||'')}</textarea><small>Correct extraction mistakes or remove outdated details here. This text stays in your browser and is sent only to the local app for generation.</small></label></details><div class="divider"></div><label class="checkbox-field"><input type="checkbox" name="reminder" ${state.profile.reminder?'checked':''}><span><strong>A gentle daily reminder</strong>Save a preferred time. This app does not send notifications.</span></label><label class="reminder-row field">Preferred time<input type="time" name="reminderTime" value="${esc(state.profile.reminderTime)}"></label><div class="form-actions"><button class="button" type="submit">Save my preferences →</button></div></form><aside>${state.legacyWorkspace?'<section class="right-card"><h2>Earlier browser save</h2><p>Notes and drafts from a previous workspace version are kept in an archive, separate from live applications.</p><button class="button secondary small" data-action="export-legacy">Download archive ↓</button></section>':''}<section class="right-card"><h2>Private by design.</h2><ul class="privacy-list"><li>Your profile stays in this browser.</li><li>Your CV is not sent to Google Translate.</li><li>Non-English job descriptions are translated with Google Translate.</li><li>Nothing here is sent to an advertiser.</li></ul><div class="button-row"><button class="button secondary small" data-action="export">Export my workspace ↓</button><button class="button secondary small" data-action="desk-restore">Restore a backup ↑</button><button class="text-button" data-action="desk-recovery">Download pre-restore recovery copy</button></div><p class="tiny-note">The export includes your profile, notes, and saved drafts. Keep it somewhere private.</p></section><section class="right-card"><h2>Make room for a new direction.</h2><p>Passed on a role too quickly? Bring dismissed opportunities back to your shortlist.</p><button class="text-button" data-action="restore-jobs">Restore passed jobs (${Object.keys(state.dismissed).length}) →</button><div class="danger-zone"><button class="text-button" data-action="reset">Reset this workspace</button><p class="tiny-note">Clear your profile, listings, and saved activity on this device.</p></div></section></aside></div>`;
}
function renderPractice(){Coaching.renderPractice();}
function render(){renderChrome();({today:renderToday,live:()=>LiveSearch.render(main),applications:renderApplications,practice:renderPractice,profile:renderProfile}[currentView])();}
function navigate(view){if(!['today','live','applications','practice','profile'].includes(view))view='today';if(location.hash!==`#${view}`)location.hash=view;else{currentView=view;render();}}
window.addEventListener('hashchange',()=>{currentView=location.hash.slice(1);if(!['today','live','applications','practice','profile'].includes(currentView))currentView='today';render();window.scrollTo(0,0);main.focus({preventScroll:true});});
function toggleSave(id){
  if(!jobById(id))return;
  const old=state.applications[id];
  if(old){
    if(old.status!=='Saved'||old.note||old.coverDraft||old.coverLetter||old.interviewPrep||state.versions.some(v=>v.job===id)){openModal(`<h2 id="modal-title">Remove this opportunity?</h2><p class="modal-description">Its application notes and saved drafts will also be removed. You can keep it and move it to Closed instead.</p><div class="button-row"><button class="button danger" data-action="remove-application" data-id="${id}">Remove from workspace</button><button class="button secondary" data-action="close-modal">Keep it</button></div>`);return;}
    delete state.applications[id];save();render();notify('Opportunity removed.',()=>{state.applications[id]=old;save();render();});
  }else{state.applications[id]=emptyApplication();recordAction(`save:${id}`);save();render();notify('Saved. Your next possibility is waiting in My applications.');}
  if(modal.open)showJob(id);
}
function languageName(code){return (jobLanguages.find(([id])=>id===code)||[code,code])[1]||code;}
function showJob(id){
  const j=jobById(id);if(!j)return;const a=state.applications[id],shared=overlap(j);
  const raw=state.jobs.find(job=>job.id===id);
  const shown=raw?.showOriginal?j.description:(j.translated_description||j.description);
  const currentLang=raw?.showOriginal?'original':(j.translation_language||state.profile.jobLanguage||'en');
  const tags=`<span class="tag">${esc(j.source)}</span>${applyTag(j)}${j.workplace_type?`<span class="tag">${esc(j.mode)}</span>`:''}${j.salary!=='Salary not listed'?`<span class="tag">${esc(j.salary)}</span>`:''}${j.employment?`<span class="tag">${esc(j.employment)}</span>`:''}${j.posted?`<span class="tag">${esc(j.posted)}</span>`:''}${matchTags(shared)}`;
  const originalLabel=j.source_language?`Original (${languageName(j.source_language)})`:'Original';
  const languageField=j.description?`<label class="field">Show description in<select id="job-language" data-job="${esc(id)}" aria-label="Description language"><option value="original" ${currentLang==='original'?'selected':''}>${esc(originalLabel)}</option>${jobLanguages.map(([code,label])=>`<option value="${esc(code)}" ${currentLang===code?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`:'';
  const translatedNote=j.translated_description&&!raw?.showOriginal?`<p class="tiny-note">Translated from ${esc(languageName(j.source_language||'the original language'))} with Google Translate. Skill matching uses both the original and this text.</p>`:'';
  openModal(`<div class="modal-job-header">${logo(j)}<div><h2 id="modal-title">${esc(j.title)}</h2><p>${esc(j.company)} · ${esc(j.location)}</p></div></div><div class="job-tags">${tags}</div>${shared.length?`<p class="match-note">${shared.length} skill${shared.length===1?'':'s'} covered by your experience, including related tools. This is not a hiring score.</p>`:''}<div class="button-row">${companyApplyLink(j)}${listingLink(j)}<button class="button" data-action="${a?'workspace':'save-job'}" data-id="${esc(id)}">${a?'Open application workspace':'Save this opportunity'} →</button><button class="button secondary" data-action="cover-letter" data-id="${esc(id)}">Write a cover letter</button><button class="button secondary" data-action="interview-prep" data-id="${esc(id)}">Prep for this interview</button><button class="button secondary" data-action="review" data-id="${esc(id)}">Compare with my profile</button></div>${languageField}${j.description?`<h3>${j.description_source==='pasted'?'Description you added':'Job description'}</h3>${translatedNote}<div class="job-description">${esc(shown)}</div>`:'<div class="notice">The search listing does not include full requirements. Open the original listing to read them, or paste its description to compare it with your profile.</div>'}<p class="tiny-note">Apply on the original website, then record your progress here. Saved listings are snapshots and may later close or change.</p>`,'YOUR NEXT OPPORTUNITY');
}
async function translateJob(id,target){
  const job=state.jobs.find(j=>j.id===id);if(!job?.description)return;
  if(target==='original'){job.showOriginal=true;save();showJob(id);return;}
  job.showOriginal=false;
  if(job.translation_language===target&&job.translated_description){save();showJob(id);return;}
  try{
    notify('Translating this description…');
    const response=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:job.description,target,source:job.source_language||'auto'})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(data.error||'Google Translate could not translate this listing.');
    job.translated_description=data.translated?data.text:job.description;
    job.translation_language=target;
    if(data.source_language)job.source_language=data.source_language;
    save();if(modal.open)showJob(id);
  }catch(error){notify(error.message);}
}
function showDismiss(id){const j=jobById(id);if(!j)return;openModal(`<h2 id="modal-title">Not quite your next step?</h2><p class="modal-description">Pass on ${esc(j.title)} at ${esc(j.company)}. You can bring it back from your profile later.</p><form id="dismiss-form" data-id="${id}"><label class="field">What feels off?<select name="reason"><option>Not the role I want</option><option>Location or work setup</option><option>Experience doesn’t fit</option><option>Just exploring something else</option></select></label><div class="form-actions"><button class="button secondary" type="button" data-action="close-modal">Keep looking</button><button class="button" type="submit">Pass on this role</button></div></form>`);}
function showWorkspace(id){
  const j=jobById(id),a=state.applications[id];if(!j||!a)return;
  const versions=state.versions.filter(v=>v.job===id);
  openModal(`<h2 id="modal-title">${esc(j.title)}</h2><p class="modal-description">${esc(j.company)} · Your application workspace</p><div class="button-row">${companyApplyLink(j)}${listingLink(j)}</div><form id="workspace-form" data-id="${id}"><div class="form-grid"><label class="field">Where are you now?<select name="status">${STATUSES.map(s=>`<option ${s===a.status?'selected':''}>${s}</option>`).join('')}</select></label><label class="field">Next-step date<input type="date" name="followup" value="${esc(a.followup)}"></label><label class="field full">Notes for your future self<textarea name="note" maxlength="5000" rows="4" placeholder="What interests you? What would you like to ask?">${esc(a.note)}</textarea></label></div><div class="form-actions"><button class="text-button" type="button" data-action="review" data-id="${id}">Compare my profile ↗</button><button class="text-button" type="button" data-action="cover-letter" data-id="${id}">Write a cover letter ↗</button><button class="text-button" type="button" data-action="interview-prep" data-id="${id}">Prep for this interview ↗</button><button class="button" type="submit">Save progress</button></div></form><p class="tiny-note">Stages and dates are for your own records. No application or reminder is sent.</p>${a.coverLetter?`<div class="divider"></div><div class="section-title"><h3>Cover letter</h3></div><pre class="cover-letter-preview">${esc(a.coverLetter)}</pre>`:''}${a.interviewPrep?`<div class="divider"></div><div class="section-title"><h3>Interview prep</h3></div><p class="modal-description">${esc(a.interviewPrep.briefing)}</p><button class="text-button" type="button" data-action="interview-prep" data-id="${id}">Open the full pack ↗</button>`:''}<div class="divider"></div><div class="section-title"><h3>Application drafts</h3></div><p class="modal-description">Keep a version of your application text for this role. Only write experience and achievements you can support.</p>${versions.length?`<ul class="version-list">${versions.map(v=>`<li><span>${esc(v.title)}<small style="display:block;color:var(--muted)">${esc(v.date)}</small></span><button class="text-button" data-action="download-version" data-id="${esc(v.id)}">Download ↓</button></li>`).join('')}</ul>`:''}<button class="button secondary" data-action="draft" data-id="${id}">Create a saved draft ↗</button>`,'ONE PLACE FOR YOUR NEXT STEP');
}
function coverLoadingMarkup(){
  const where=parseDevice==='gpu'?'GPU':'CPU';
  return `<div class="cv-loading" role="status"><div class="cv-loading-mark" aria-hidden="true"><i></i></div><strong>Writing from your experience</strong><p>The local model is drafting a note from your profile and this listing. This can take a minute on ${where}.</p></div>`;
}
function coverLanguage(job){
  const raw=state.jobs.find(item=>item.id===job.id);
  if(raw?.showOriginal)return raw.source_language||'en';
  return job.translation_language||state.profile.jobLanguage||'en';
}
function ensureSaved(id){
  if(state.applications[id])return;
  state.applications[id]=emptyApplication();
  recordAction(`save:${id}`);
}
function showCoverLetter(id,letter='',error=''){Coaching.showLetter(id,letter,error);}
async function generateCoverLetter(id){return Coaching.generateLetter(id);}

function profilePayload(id){
  const bg=state.profile.background||emptyBackground();
  return {name:state.profile.name,location:state.profile.location,mode:state.profile.mode,roles:state.profile.roles,skills:state.profile.skills,years_experience:bg.yearsExperience,recent_titles:bg.recentTitles,employers:bg.employers,certifications:bg.certifications,industry:bg.industry,cv_text:bg.cvText,achievements:bg.achievements||'',note:state.applications[id]?.note||'',motivation:state.applications[id]?.motivation||''};
}
function jobPayload(id){
  const j=jobById(id),raw=state.jobs.find(item=>item.id===id);
  return {title:j.title,company:j.company,location:j.location==='Location not listed'?'':j.location,workplace_type:raw.workplace_type||'',description:JobStore.displayedDescription(raw)||raw.description||'',language:coverLanguage(j)};
}
function prepLoadingMarkup(){
  const where=parseDevice==='gpu'?'GPU':'CPU';
  if(parseMode==='local-model')return `<div class="cv-loading" role="status"><div class="cv-loading-mark" aria-hidden="true"><i></i></div><strong>Building interview prep</strong><p>Building an evidence-based learning plan and interview prompts for this role. This can take a minute on ${where}.</p></div>`;
  return `<div class="cv-loading" role="status"><div class="cv-loading-mark" aria-hidden="true"><i></i></div><strong>Matching open materials</strong><p>Turning the job requirements and CV evidence into focused practice sessions. No model is needed for the learning plan.</p></div>`;
}
function prepBody(pack,id){
  const stories=pack.stories.length?`<ol class="prep-stories">${pack.stories.map(s=>`<li><p>${esc(s.prompt)}</p>${s.anchor?`<small>Pull this from: ${esc(s.anchor)}</small>`:''}</li>`).join('')}</ol>`:'';
  const resources=pack.resources.length?`<ul class="prep-resources">${pack.resources.map(r=>`<li><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)} ↗</a><p>${esc(r.blurb)}</p></li>`).join('')}</ul>`:'';
  const ask=pack.ask_them.length?`<ul class="prep-ask">${pack.ask_them.map(q=>`<li>${esc(q)}</li>`).join('')}</ul>`:'';
  const note=pack.generated?'Story prompts were written from your profile for this listing. Say them out loud; do not memorize a script.':'The self-guided sessions work without AI. With a local model, you can tailor one exercise at a time.';
  return `${Coaching.planMarkup(id,pack)}${pack.briefing?`<p class="modal-description">${esc(pack.briefing)}</p>`:''}${stories?`<h3>Stories from your work</h3><p class="tiny-note">Answer with real examples. The prompts are not the answers.</p>${stories}`:''}${resources?`<h3>Open practice materials</h3><p class="tiny-note">Public docs and open-source guides matched to this role. Use the relevant sections alongside your practice sessions.</p>${resources}`:''}${ask?`<h3>Questions to ask them</h3>${ask}`:''}<p class="tiny-note">${esc(note)}</p>`;
}
function showInterviewPrep(id, pack=null, error=''){
  const j=jobById(id);if(!j)return;
  if(!state.profile.name){notify('Add your name in My profile first.');navigate('profile');return;}
  if(!(j.description||'').trim()){showReview(id);notify('Paste the job description first so prep can talk about this role.');return;}
  if(!serverAvailable()){
    openModal(`<h2 id="modal-title">Interview prep for this role.</h2><p class="modal-description">${esc(j.title)} at ${esc(j.company)}</p><div class="notice">Start the local app with <code>python -m ats_matcher.server</code> and open <code>http://127.0.0.1:8765</code> so we can match open materials to this listing.</div><div class="button-row"><button class="button secondary" data-action="job" data-id="${esc(id)}">Back to the listing</button></div>`,'INTERVIEW PREP');
    return;
  }
  const existing=pack||state.applications[id]?.interviewPrep||null;
  if(!existing&&!error){generateInterviewPrep(id);return;}
  openModal(`<h2 id="modal-title">Interview prep for this role.</h2><p class="modal-description">${esc(j.title)} at ${esc(j.company)}</p>${error?`<div class="notice warning">${esc(error)}</div>`:''}${Coaching.staleMarkup(id,'prep')}${existing?prepBody(existing,id):''}<div class="button-row"><button class="button" data-action="retry-interview-prep" data-id="${esc(id)}">${existing?'Rebuild from my latest profile':'Try again'} →</button>${existing?`<button class="button secondary" data-action="coaching-export" data-id="${esc(id)}">Download my practice ↓</button>`:''}<button class="text-button" data-action="${state.applications[id]?'workspace':'job'}" data-id="${esc(id)}">Back</button></div>`,'INTERVIEW PREP');
}
async function generateInterviewPrep(id){
  const j=jobById(id);if(!j)return;
  ensureSaved(id);save();
  openModal(`<h2 id="modal-title">Building your role practice.</h2><p class="modal-description">${esc(j.title)} at ${esc(j.company)}</p>${prepLoadingMarkup()}<p class="tiny-note">Your previous plan and answers are kept. Closing this window stops waiting for the result.</p>`,'INTERVIEW PREP');
  try{
    const result=await Coaching.request('/api/interview-prep',id,{refresh:(prepRefresh[id]||0)%51});
    if(!result)return;
    const pack=readPrep(result.data);if(!pack)throw Error('No usable practice plan was returned.');
    prepRefresh[id]=(prepRefresh[id]||0)+1;
    state.applications[id].interviewPrep=pack;
    state.applications[id].prepSource=result.source;
    state.applications[id].updated=today;
    recordAction(`prep:${id}`);save();showInterviewPrep(id,pack);
  }catch(error){showInterviewPrep(id,state.applications[id]?.interviewPrep||null,error.message);}
}

function showReview(id){
  const j=jobById(id);if(!j)return;
  const found=(()=>{const body=[j.translated_description,j.description].filter(Boolean).join('\n');return body?JobStore.mentionedSkills(body,state.profile.skills):j.skills;})();
  const compared=JobStore.compareSkills(found,state.profile.skills);
  const coveredList=compared.matched.length?`<ul>${compared.matched.map(item=>`<li>${esc(item.name)}${item.via.length?`<small>related to ${item.via.slice(0,3).map(esc).join(', ')}</small>`:''}</li>`).join('')}</ul>`:'<p>No overlapping tools found yet. Check that your profile includes the work you actually do.</p>';
  const missingList=compared.missing.length?`<ul>${compared.missing.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:'<p>No extra named tools beyond what your profile already covers.</p>';
  openModal(`<h2 id="modal-title">Compare the role with your experience.</h2><p class="modal-description">${esc(j.title)} at ${esc(j.company)}</p><div class="button-row">${companyApplyLink(j)}${listingLink(j)}</div><form id="description-form" data-id="${esc(id)}"><label class="field field-row">${j.description&&j.description_source!=='pasted'?'Edit the description if you want a closer comparison':'Paste the job description'}<textarea name="description" required maxlength="20000" rows="6" placeholder="Copy the requirements from the original listing.">${esc(j.description||'')}</textarea><small>The original listing text stays in your browser. Changing the description language sends that text to Google Translate.</small></label><button class="button secondary" type="submit">${j.description?'Update comparison →':'Save description and compare →'}</button></form>${j.description||found.length?`<div id="role-evidence"><div class="review-grid"><div class="review-box"><h3>Covered by your experience</h3>${coveredList}</div><div class="review-box missing"><h3>Named in the listing, not in your profile</h3>${missingList}</div></div><div class="notice">Related tools count: GitHub Actions, Jenkins, or GitLab CI/CD cover CI/CD. Generic posting language such as Communication is ignored. Different clouds or shells still count as gaps. Read the description yourself; this is not a hiring score.</div></div>`:'<div class="notice">Add the description to start a comparison. Search cards alone do not give us the requirements.</div>'}<div class="button-row"><button class="button" data-action="${state.applications[id]?'workspace':'save-job'}" data-id="${esc(id)}">${state.applications[id]?'Back to workspace':'Save opportunity'} →</button></div>`,'YOUR EXPERIENCE, IN CONTEXT');
  Coaching.loadComparison(id);
}
function showDraft(id){const j=jobById(id);if(!j||!state.applications[id])return;openModal(`<h2 id="modal-title">Make this application your own.</h2><p class="modal-description">Save application text for ${esc(j.title)} at ${esc(j.company)}. This is a draft editor, not an automatic CV rewrite.</p><form id="draft-form" data-id="${id}"><label class="field">Draft name<input name="title" maxlength="100" required value="${esc(j.company)} - first draft"></label><label class="field field-row">Your application text<textarea name="body" required maxlength="20000" rows="9" placeholder="Write or paste your application text here. Highlight real examples that fit this role."></textarea></label><div class="form-actions"><button class="button" type="submit">Save this draft →</button></div></form>`,'APPLICATION DRAFT');}
function showExercise(id,revealed=false){
  const e=EXERCISES.find(e=>e.id===id);if(!e)return;
  openModal(`<h2 id="modal-title">${e.title}</h2><p class="modal-description">${e.minutes} minutes · ${e.topic}</p><div class="question">${e.question}</div><label class="field">Give it a try<textarea id="practice-answer" data-exercise="${id}" maxlength="5000" rows="4" placeholder="No need to make it perfect. Start with your own words.">${esc(state.answers[id]||'')}</textarea><small>Your answer saves as you type.</small></label>${revealed?`<div class="worked-answer"><strong>One way to approach it</strong>${e.answer}${e.code?`<pre>${esc(e.code)}</pre>`:''}<p style="margin:12px 0 0;font-size:12px">${e.prompt}</p></div><div class="form-actions"><button class="button" data-action="complete-exercise" data-id="${id}">Mark practice complete ✓</button></div>`:`<div class="form-actions"><button class="button" data-action="reveal-answer" data-id="${id}">See an example approach →</button></div>`}`,'A FEW MINUTES FOR YOURSELF');
}
function importHint(){
  if(parseMode==='local-model')return parseDevice==='gpu'?'PDF, Word, and text CVs are read by the local model on GPU - the same AI matcher as ats-match parse. You’ll check suggested roles before we search.':'PDF, Word, and text CVs are read by the local model - the same AI matcher as ats-match parse. You’ll check suggested roles before we search.';
  if(parseMode==='basic')return 'The app is using basic document reading. Restart with --mode cpu or --mode gpu to use AI matching.';
  if(parseMode==='unavailable')return 'The language model is not loaded. Place a GGUF in .models, set LLAMA_MODEL_PATH, or pass --model, then restart the app.';
  return 'Text and exported profiles open directly. PDF and Word need the local app server; instructions appear if it isn’t running.';
}
function showOnboarding(){importEpoch++;importDraft=null;importText='';openModal(`<div class="onboard-steps"><strong>01 Bring your experience</strong><span>→</span><span>02 Choose your direction</span></div><h2 id="modal-title">Let’s make this feel like you.</h2><p class="modal-description">Bring a CV or start with a few details. You’ll check everything before it becomes your profile.</p><div class="upload-zone"><div class="upload-symbol" aria-hidden="true">↥</div><strong>A little experience goes a long way.</strong><p>PDF, Word, text, or an exported CV profile · up to 5 MB</p><label class="field"><span>Choose your CV</span><input type="file" id="cv-file" accept=".pdf,.docx,.txt,.json"></label></div><div id="import-status" role="status" aria-live="polite"><p class="tiny-note">${esc(importHint())}</p></div><div class="form-actions"><button class="text-button" data-action="close-modal">Back to my workspace</button><button class="button" id="continue-import" data-action="confirm-import">Start with my details →</button></div><p class="tiny-note">Your original CV file is not saved by the app. Confirmed profile details are stored in this browser.</p>`,'WELCOME TO YOUR NEXT CHAPTER');}
function importedProfile(raw){
  const p=raw?.user_profile||raw;
  if(!p||typeof p!=='object'||Array.isArray(p)||!['full_name','skills','possible_titles','recent_titles'].some(k=>k in p))throw Error('This file does not look like a CV profile. Choose the JSON file created by ats-match parse.');
  return {name:text(p.full_name,80),skills:strings(p.skills),roles:strings(p.possible_titles).length?strings(p.possible_titles).slice(0,8):strings(p.recent_titles).slice(0,8),location:JobStore.formatLocation(p.location),mode:'Any',goal:5,reminder:false,reminderTime:'09:00',jobLanguage:state.profile.jobLanguage||'en',background:readBackground({...p,cv_text:p.cv_text||p.cvText||''})};
}
function textProfile(body){
  const skills=JobStore.mentionedSkills(body);
  const first=body.split(/\r?\n/).find(l=>l.trim())?.trim()||'';
  return {name:first.length<70&&!/[@\d]/.test(first)?first:'',skills,roles:[],location:'',mode:'Any',goal:5,reminder:false,reminderTime:'09:00',jobLanguage:state.profile.jobLanguage||'en',background:{...emptyBackground(),cvText:text(body,12000)}};
}
function cvLoadingMarkup(){
  if(parseMode==='basic')return '<div class="cv-loading" role="status"><div class="cv-loading-mark" aria-hidden="true"><i></i></div><strong>Reading your CV</strong><p>You’ll be able to check the details next.</p></div>';
  const where=parseDevice==='gpu'?'GPU':'CPU';
  return `<div class="cv-loading" role="status"><div class="cv-loading-mark" aria-hidden="true"><i></i></div><strong>Matching your experience</strong><p>The model is reading your CV and suggesting roles. This can take a minute on ${where}.</p></div>`;
}
async function importFile(file){
  if(!file)return;const epoch=++importEpoch;const status=$('#import-status'),next=$('#continue-import');
  importDraft=null;importText='';next.disabled=true;next.textContent='Reading your CV…';status.innerHTML=cvLoadingMarkup();
  try{
    if(file.size>5*1024*1024)throw Error('Please choose a file smaller than 5 MB.');
    if(!file.size)throw Error('This file is empty. Please choose a CV with some text.');
    const extension=file.name.split('.').pop().toLowerCase();let draft,body='',message='Your CV was read. Check the details and add anything we missed.';
    if(extension==='json')draft=importedProfile(JSON.parse(await file.text()));
    else if(['pdf','docx','txt'].includes(extension)){
      if(!serverAvailable()){
        if(extension!=='txt')throw Error('For PDF or Word, start the local app with: python -m ats_matcher.server. Then open http://127.0.0.1:8765. You can also import a text CV or exported JSON here.');
        body=await file.text();draft=textProfile(body);message='We found some words from your text CV. Check your name, skills, and preferred roles before saving.';
      }else{
        const response=await fetch('/api/parse',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-CV-Extension':extension},body:file});
        const result=await response.json().catch(()=>{throw Error('The CV reader is not connected. Start the app with: python -m ats_matcher.server, then open http://127.0.0.1:8765.');});
        if(!response.ok)throw Error(result.error||'This CV could not be read. Try a text CV instead.');
        draft=importedProfile({...result.profile,cv_text:result.text||''});body=result.text||'';
        if(result.mode==='local-model')message='The local model read your CV and suggested roles for job matching. Check everything before we search.';
        else{const detected=textProfile(body);draft={...draft,name:draft.name||detected.name,skills:draft.skills.length?draft.skills:detected.skills,roles:draft.roles.length?draft.roles:detected.roles};message='Your document was read locally. Basic reading found some details; check your name and skills, then choose the roles you want.';}
        if(result.quality==='low')message='Very little text could be read. This may be a scanned CV. You can add your details manually or try a text-based PDF.';
      }
    }else throw Error('Choose a PDF, Word (.docx), text, or exported JSON profile.');
    if(epoch!==importEpoch||!modal.open)return;
    importDraft=draft;importText=body;status.innerHTML=`<div class="notice">${esc(message)}</div>`;next.textContent='Check my details →';
  }catch(error){if(epoch!==importEpoch||!modal.open)return;status.innerHTML=`<div class="notice error">${esc(error.message)}</div>`;next.textContent='Enter my details instead →';}
  finally{if(epoch===importEpoch&&modal.open)next.disabled=false;}
}
function confirmImport(){const p=importDraft||{...initialProfile,jobLanguage:state.profile.jobLanguage||'en'};openModal(`<div class="onboard-steps"><span>01 Bring your experience</span><span>→</span><strong>02 Choose your direction</strong></div><h2 id="modal-title">Your next chapter starts here.</h2><p class="modal-description">Check what we found, make it yours, and choose what you’d like to explore. Your confirmed roles and location will be used to search for real jobs.</p><form id="onboarding-form">${profileFields(p)}<div class="form-actions"><button class="button secondary" type="button" data-action="onboard">Back</button><button class="button" type="submit">Show my shortlist →</button></div></form>`,'MAKE IT YOURS');}
function readProfile(form){const f=new FormData(form);return {name:String(f.get('name')).trim(),location:String(f.get('location')).trim(),roles:split(f.get('roles')).slice(0,8),skills:split(f.get('skills')),mode:String(f.get('mode')),goal:Math.min(20,Math.max(1,Number(f.get('goal'))||5)),reminder:f.get('reminder')==='on',reminderTime:String(f.get('reminderTime')||'09:00'),jobLanguage:jobLanguages.some(([id])=>id===String(f.get('jobLanguage')))?String(f.get('jobLanguage')):'en',background:form.id==='onboarding-form'?(importDraft?.background||emptyBackground()):(state.profile.background||emptyBackground())};}
function download(name,body,type='text/plain'){const url=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}

document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const action=button.dataset.action,id=button.dataset.id;
  switch(action){
    case 'theme':toggleTheme();break;
    case 'navigate':closeModal();navigate(button.dataset.view);break;
    case 'close-modal':closeModal();break;
    case 'onboard':showOnboarding();break;
    case 'confirm-import':confirmImport();break;
    case 'job':showJob(id);break;
    case 'save-job':toggleSave(id);break;
    case 'workspace':showWorkspace(id);break;
    case 'dismiss':showDismiss(id);break;
    case 'review':showReview(id);break;
    case 'cover-letter':showCoverLetter(id);break;
    case 'retry-cover-letter':generateCoverLetter(id);break;
    case 'interview-prep':showInterviewPrep(id);break;
    case 'retry-interview-prep':generateInterviewPrep(id);break;
    case 'copy-cover-letter':{const body=document.getElementById('cover-letter-text')?.value||'';if(!body)break;if(navigator.clipboard?.writeText)navigator.clipboard.writeText(body).then(()=>notify('Copied. Check it before you send it.')).catch(()=>notify('Copy the text from the box.'));else notify('Copy the text from the box.');break;}
    case 'save-cover-letter':{Coaching.captureLetter(id);const body=document.getElementById('cover-letter-text')?.value.trim();if(!body){notify('There is no letter to save yet.');break;}ensureSaved(id);state.applications[id].coverLetter=body;state.applications[id].updated=today;state.versions.push({id:`draft-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,job:id,title:`Cover letter · ${(jobById(id)||{}).company||'role'}`,body,date:today});state.versions=state.versions.slice(-30);recordAction(`letter:${id}`);save();showWorkspace(id);notify('Letter saved with this opportunity. Read it before you send anything.');break;}
    case 'draft':showDraft(id);break;
    case 'download-version':{const v=state.versions.find(v=>v.id===id);if(v)download(`${v.title.replace(/[^a-z0-9-]/gi,'_').slice(0,60)}.txt`,v.body);break;}
    case 'exercise':showExercise(id);break;
    case 'reveal-answer':showExercise(id,true);break;
    case 'complete-exercise':if(!state.completed.includes(id)){state.completed.push(id);recordAction(`practice:${id}`);}state.tasks[`${today}:practice`]=true;save();closeModal();render();notify('A little more prepared. Nice work making time for yourself.');break;
    case 'filter':activeFilter=button.dataset.filter;renderToday();break;
    case 'clear-filters':activeFilter='All';searchTerm='';renderToday();break;
    case 'focus-job':{const j=sortedJobs()[0];if(j)showJob(j.id);else navigate('live');break;}
    case 'refresh-jobs':refreshShortlist();break;
    case 'export-legacy':if(state.legacyWorkspace)download('previous-workspace.json',JSON.stringify(state.legacyWorkspace,null,2),'application/json');break;
    case 'task':{const key=`${today}:${id}`;state.tasks[key]=!state.tasks[key];if(state.tasks[key])recordAction(`task:${id}`);else state.actions=state.actions.filter(a=>!(a.day===today&&a.id===`task:${id}`));save();render();break;}
    case 'restore-jobs':state.dismissed={};save();render();notify('Passed opportunities are back in your shortlist.');break;
    case 'remove-application':{const old=state.applications[id],versions=state.versions.filter(v=>v.job===id);delete state.applications[id];state.versions=state.versions.filter(v=>v.job!==id);save();closeModal();render();notify('Opportunity and its notes removed.',()=>{state.applications[id]=old;state.versions.push(...versions);save();render();});break;}
    case 'export':download('my-ats-workspace.json',JSON.stringify(state,null,2),'application/json');notify('Your workspace export is ready. Keep it somewhere private.');break;
    case 'reset':openModal('<h2 id="modal-title">Start fresh?</h2><p class="modal-description">This clears the profile, saved opportunities, notes, answers, and drafts stored by this app. Export your workspace first if you want to keep a copy.</p><div class="button-row"><button class="button danger" data-action="confirm-reset">Clear and start fresh</button><button class="button secondary" data-action="close-modal">Keep my workspace</button></div>');break;
    case 'confirm-reset':try{localStorage.removeItem(KEY+':before-restore');}catch{}Coaching.cancel();searchEpoch++;LiveSearch.reset();shortlistError='';state=freshState();activeFilter='All';searchTerm='';save();closeModal();navigate('today');notify('Your workspace is clear. Search for your next opportunity.');break;
    case 'help':openModal(`<h2 id="modal-title">Your local job-search workspace.</h2><p class="modal-description">Search live jobs, save opportunities, track applications, write cover letters, and practice interviews. Your changes stay in this browser.</p><div class="notice">Apply through each listing’s original website. Notes and drafts stay on this device. Skill comparisons cover related tools, not just identical names. Cover letters and tailored exercises use the local model. Foundation sessions, refreshers, people-skill rehearsals, and self-checks also work without it. Practice never adds skills to your CV automatically. CV import uses the same local AI matcher as <code>ats-match parse</code>.</div><h3>Bring your own experience</h3><p class="modal-description">${esc(importHint())} Start the local app with <code>python -m ats_matcher.server</code> and open <code>http://127.0.0.1:8765</code>.</p><button class="button" data-action="onboard">Import a CV →</button>`,'ABOUT THIS APP');break;
  }
});
document.addEventListener('input',event=>{
  if(event.target.id==='search-jobs'){searchTerm=event.target.value;renderJobList();}
  if(event.target.id==='practice-answer'){state.answers[event.target.dataset.exercise]=event.target.value;persist();}
});
document.addEventListener('change',event=>{
  if(event.target.id==='cv-file')importFile(event.target.files[0]);
  if(event.target.id==='job-language')translateJob(event.target.dataset.job,event.target.value);
  if(event.target.dataset.statusJob){const id=event.target.dataset.statusJob,status=event.target.value;if(!state.applications[id]||!STATUSES.includes(status))return;state.applications[id].status=status;state.applications[id].updated=today;recordAction(`stage:${id}:${status}`);save();render();notify(`Moved to ${status}. No application has been sent.`);}
});
document.addEventListener('submit',event=>{
  const form=event.target;if(!['profile-form','onboarding-form','workspace-form','dismiss-form','draft-form','description-form'].includes(form.id))return;event.preventDefault();const f=new FormData(form),id=form.dataset.id;
  if(form.id==='profile-form'||form.id==='onboarding-form'){
    const p=readProfile(form);if(!p.name){form.elements.name.setCustomValidity('Please enter your name.');form.elements.name.reportValidity();form.elements.name.addEventListener('input',()=>form.elements.name.setCustomValidity(''),{once:true});return;}
    if(form.id==='profile-form')p.background=Coaching.readCareerFields(form,p.background);
    if(form.id==='onboarding-form'&&state.sample)state=freshState();state.profile=p;state.sample=false;if(form.id==='onboarding-form'){importDraft=null;importText='';activeFilter='All';searchTerm='';}
    save();closeModal();if(form.id==='onboarding-form'){LiveSearch.reset(true);navigate('today');refreshShortlist(true);}else{render();notify('Preferences saved. Start a new search to use your updated roles, location, and description language.');LiveSearch.reset(true);}
  }
  if(form.id==='description-form'){const job=state.jobs.find(j=>j.id===id),description=String(f.get('description')).trim();if(!job||!description)return;job.description=description;job.description_source='pasted';job.skills=JobStore.mentionedSkills(description,state.profile.skills);job.translated_description=null;job.translation_language=null;job.showOriginal=false;save();showReview(id);}
  if(form.id==='workspace-form'){const old=state.applications[id];if(!old)return;const status=String(f.get('status'));if(status!==old.status)recordAction(`stage:${id}:${status}`);state.applications[id]={...old,status,note:String(f.get('note')),followup:String(f.get('followup')),updated:today,coverLetter:old.coverLetter||'',interviewPrep:old.interviewPrep||null};save();closeModal();render();notify('Progress saved. One less thing to keep in your head.');}
  if(form.id==='dismiss-form'){state.dismissed[id]=String(f.get('reason'));save();closeModal();render();notify('Passed for now.',()=>{delete state.dismissed[id];save();render();});}
  if(form.id==='draft-form'){const body=String(f.get('body')).trim(),title=String(f.get('title')).trim();if(!body||!title){notify('Add a draft name and some application text first.');return;}state.versions.push({id:`draft-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,job:id,title,body,date:today});state.versions=state.versions.slice(-30);recordAction(`draft:${id}`);save();showWorkspace(id);notify('Draft saved to this application workspace.');}
});
modal.addEventListener('cancel',()=>{importEpoch++;Coaching.cancel();});
modal.addEventListener('click',event=>{if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();}});
currentView=['today','live','applications','practice','profile'].includes(location.hash.slice(1))?location.hash.slice(1):'today';
persist();
render();
applyTheme(preferredTheme());
loadServerStatus();
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{
  try{const saved=localStorage.getItem(THEME_KEY);if(saved==='dark'||saved==='light')return;}catch{}
  applyTheme(preferredTheme());
});
