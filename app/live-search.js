/* Live search feeds the shared shortlist and application workspace. */
const LiveSearch = (() => {
  let query = null, result = null, loading = false, error = '', generation = 0;
  let sources = [{id:'linkedin',label:'LinkedIn'}];
  const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const options = (rows,selected) => rows.map(([value,label])=>`<option value="${escape(value)}" ${String(selected??'')===String(value)?'selected':''}>${escape(label)}</option>`).join('');
  const choices = (name,label,rows,selected) => {
    const picked=Array.isArray(selected)?selected:[selected];
    return `<fieldset class="live-choices"><legend>${label}</legend><small>Choose any that suit you. Leave blank for all.</small><div>${rows.map(([value,text])=>`<label class="checkbox-field"><input type="checkbox" name="${name}" value="${value}" ${picked.includes(value)?'checked':''}>${text}</label>`).join('')}</div></fieldset>`;
  };
  const safeLink = value => {try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?escape(url.href):'';}catch{return '';}};
  const getDateDefault = provider => provider==='linkedin'?'past_week':'any';
  function defaults(){const q=state.shortlist.query?{...state.shortlist.query}:searchFromProfile();if(!q.date_since_posted){q.date_since_posted=getDateDefault(q.providers?.[0]||'linkedin');}return q;}
  function reset(useProfile=false){generation++;searchEpoch++;query=useProfile?searchFromProfile():null;result=null;error='';loading=false;}
  function render(target){
    const q=query||defaults();
    const filtersOpen=document.querySelector('.live-filters')?.open||false;
    target.innerHTML=heading("Find a role worth saving.","Search public job sources by role, place, and the way you want to work.",`<button class="button secondary" data-action="desk-add-job">Add a role from another site +</button>`)+`<form id="live-search-form" class="form-card"><div class="form-grid"><label class="field">Role or keywords<input name="keywords" required maxlength="300" value="${escape(q.keywords)}" placeholder="For example, software engineer"></label><label class="field">Location<input name="location" maxlength="200" value="${escape(q.location)}" placeholder="Berlin, Germany"></label><label class="field">Source<select name="provider" data-preferred-source="${escape(q.providers?.[0]||'linkedin')}">${options(sources.map(s=>[s.id,s.label]),q.providers?.[0])}</select></label><label class="field" id="live-career-url">Company career URL (optional)<input name="career_url" maxlength="2000" value="${escape(q.career_url)}" placeholder="https://boards.greenhouse.io/stripe"><small>Search one hosted board from the selected source.</small></label><p class="tiny-note" id="live-source-note"></p>${choices('workplace_type','Work arrangement',[['remote','Remote'],['hybrid','Hybrid'],['on_site','On-site']],q.workplace_type)}</div><details class="live-filters" ${filtersOpen?'open':''}><summary>More search options</summary><div class="form-grid"><label class="field">Posted within<select name="date_since_posted">${options([['24hr','24 hours'],['past_week','Past week'],['past_month','Past month'],['any','Any time'],['custom','Choose number of days']],q.posted_within_days?'custom':q.date_since_posted)}</select></label><label class="field" id="live-custom-days" ${q.posted_within_days?'':'hidden'}>Number of days<input type="number" name="posted_within_days" min="1" max="365" step="1" value="${q.posted_within_days||3}" ${q.posted_within_days?'required':'disabled'}><small>For example, 3 finds jobs posted in the last three days.</small></label>${choices('job_type','Job type',[['full_time','Full time'],['part_time','Part time'],['contract','Contract'],['temporary','Temporary'],['volunteer','Volunteer'],['internship','Internship']],q.job_type)}${choices('experience_level','Experience level',[['internship','Internship'],['entry_level','Entry level'],['associate','Associate'],['senior','Senior'],['director','Director'],['executive','Executive']],q.experience_level)}<label class="field">LinkedIn salary band<select name="salary">${options([['','Any salary'],['40000','40,000+'],['60000','60,000+'],['80000','80,000+'],['100000','100,000+'],['120000','120,000+']],q.salary)}</select><small>Availability and currency depend on the market. This is a source filter, not a salary guarantee.</small></label><label class="field">Description language<select name="translate_to">${options(typeof jobLanguages!=='undefined'?jobLanguages:[['en','English']],q.translate_to||(typeof state!=='undefined'&&state.profile.jobLanguage)||'en')}</select><small>Non-English listings are translated with Google Translate. The original text is kept.</small></label><label class="field">Sort by<select name="sort_by">${options([['relevant','Relevance'],['recent','Most recent']],q.sort_by)}</select></label><label class="field">Maximum results<input type="number" name="limit" required min="1" max="100" value="${q.limit}"></label><label class="field">Starting page<input type="number" name="page" required min="0" max="1000" value="${q.page}"><small>Pages start at 0. LinkedIn uses 25-position offsets; other sources use the maximum results per page.</small></label><div><label class="checkbox-field"><input type="checkbox" name="has_verification" ${q.has_verification?'checked':''}> Verified listings filter</label><label class="checkbox-field" style="margin-top:12px"><input type="checkbox" name="under_10_applicants" ${q.under_10_applicants?'checked':''}> Fewer than 10 applicants filter</label></div></div></details><div class="form-actions"><span class="tiny-note">Only these search terms and filters go to the job source. Non-English descriptions are sent to Google Translate. Your CV is not sent.</span><button class="button" type="submit" ${loading?'disabled':''}>${loading?'Searching…':'Search live jobs →'}</button></div></form><div id="live-results" aria-live="polite" aria-busy="${loading}"></div>`;
    syncSourceFields();
    renderResults();
  }
  function renderResults(){
    const box=document.getElementById('live-results');if(!box)return;
    box.setAttribute('aria-busy',String(loading));
    if(loading){box.innerHTML='<div class="notice">Checking the selected job source and reading public job descriptions. Larger searches can take a little longer.</div>';return;}
    if(error){box.innerHTML=`<div class="notice error"><strong>Search couldn’t complete.</strong> ${escape(error)}</div>`;return;}
    if(!result){box.innerHTML='<div class="notice">Search results also appear in My daily shortlist. Save an opportunity to track it in My applications.</div>';return;}
    const meta=result.jobs_meta;
    const jobs=result.jobs.map(JobStore.normalize).filter(Boolean).map(j=>jobById(j.id)).filter(Boolean);
    box.innerHTML=`<div class="section-title" style="margin-top:28px"><h2>${meta.status==='error'?'The source could not complete this search':`${jobs.length} live opportunit${jobs.length===1?'y':'ies'}`}</h2><small>${meta.providers.map(s=>`${escape(s.provider)}${s.cached?' · cached':''}`).join(' / ')}</small></div>${[...(meta.errors||[]),...(meta.warnings||[])].map(message=>`<div class="notice warning">${escape(message)}</div>`).join('')}<div class="job-list">${jobs.map(jobCard).join('')||(meta.status==='error'?'':'<div class="empty-state"><h3>No listings were returned.</h3><p>Try different keywords, a broader location, or fewer filters.</p></div>')}</div>${meta.providers.length===1&&meta.status!=='error'&&meta.providers[0].next_page!==null&&meta.providers[0].next_page<=1000?`<div class="form-actions"><button type="button" class="button secondary" id="live-next-page" data-page="${meta.providers[0].next_page}">Next source page →</button></div>`:''}<p class="subtle-caption">Public job sources can be limited or unavailable. Listings and filter behavior are controlled by the source. No automatic applications are sent.</p>`;
  }
  async function search(values){
    query=values;error='';result=null;loading=true;const request=++generation,workspaceRequest=++searchEpoch;
    const button=document.querySelector('#live-search-form button[type=submit]');if(button){button.disabled=true;button.textContent='Searching…';}renderResults();
    try{
      if(!/^https?:$/.test(location.protocol))throw Error('Start the local app with python -m ats_matcher.server, then open its localhost address. Live search needs the local server.');
      const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});
      const payload=await response.json().catch(()=>{throw Error('The local job-search API is not available here. Start python -m ats_matcher.server on a free port and use that address.');});
      if(request!==generation||workspaceRequest!==searchEpoch)return;
      if(payload.jobs_meta){
        if(payload.jobs_meta.status!=='error'&&!receiveJobs(payload,values))throw Error(shortlistError||'The listings could not be read. Please try again.');
        result=payload;
      }
      else if(!response.ok)throw Error(payload.error||'The job source is unavailable.');
      else throw Error('The server returned an unexpected search result.');
    }catch(e){if(request===generation)error=e.message;}
    finally{if(request===generation){loading=false;if(document.getElementById('live-search-form'))render(document.getElementById('main'));}}
  }
  document.addEventListener('submit',event=>{
    if(event.target.id!=='live-search-form')return;event.preventDefault();
    const form=new FormData(event.target),values=Object.fromEntries(form.entries());
    values.providers=[values.provider];delete values.provider;
    if(!values.career_url?.trim())delete values.career_url;
    for(const key of ['job_type','workplace_type','experience_level']){
      const selected=form.getAll(key);if(selected.length)values[key]=selected;else delete values[key];
    }
    if(!values.salary)delete values.salary;
    if(values.date_since_posted==='custom')values.date_since_posted='any';else delete values.posted_within_days;
    for(const key of ['limit','page','salary','posted_within_days'])if(values[key]!==undefined)values[key]=Number(values[key]);
    values.has_verification=form.has('has_verification');values.under_10_applicants=form.has('under_10_applicants');
    search(values);
  });
  document.addEventListener('change',event=>{
    if(!event.target.closest('#live-search-form'))return;
    if(event.target.name==='provider'){event.target.dataset.changed='true';syncSourceFields();return;}
    if(event.target.name!=='date_since_posted')return;
    const custom=event.target.value==='custom',label=document.getElementById('live-custom-days'),input=label.querySelector('input');
    label.hidden=!custom;input.disabled=!custom;input.required=custom;
  });
  document.addEventListener('click',event=>{const button=event.target.closest('#live-next-page');if(button&&!loading)search({...query,page:Number(button.dataset.page)});});
  function syncSourceFields(){
    const form=document.getElementById('live-search-form');if(!form)return;
    const source=form.elements.provider.value,companyBoard=['greenhouse','lever','ashby'].includes(source);
    const career=form.elements.career_url;career.disabled=!companyBoard;career.closest('label').hidden=!companyBoard;
    for(const name of ['salary','experience_level','has_verification','under_10_applicants']){
      form.querySelectorAll(`[name="${name}"]`).forEach(input=>{input.disabled=source!=='linkedin';});
    }
    form.querySelectorAll('[name="workplace_type"]').forEach(input=>{
      input.disabled=source==='greenhouse'||(source==='indeed'&&input.value!=='remote');
    });
    form.querySelectorAll('[name="job_type"]').forEach(input=>{
      input.disabled=source==='greenhouse'||(source==='freehire'&&['temporary','volunteer'].includes(input.value));
    });
    const notes={
      linkedin:'Search public guest listings on LinkedIn.',
      greenhouse:'Search configured company boards (Stripe by default), or paste a Greenhouse board URL. Location matches listing text. Filters exclude jobs with missing details.',
      lever:'Search configured company boards (Palantir by default), or paste a Lever board URL. Location matches listing text. Filters exclude jobs with missing details.',
      ashby:'Search configured company boards (OpenAI by default), or paste an Ashby board URL. Location matches listing text. Filters exclude jobs with missing details.',
      freehire:'Search the Freehire catalogue. Location is matched within each page; continue to the next page for more matches.',
      indeed:'Requires the optional Indeed package. Country comes from server settings. Some filters apply within each source page.'
    };
    document.getElementById('live-source-note').textContent=notes[source]||'';
  }
  async function loadSources(){if(!/^https?:$/.test(location.protocol))return;try{const r=await fetch('/api/providers');if(r.ok){const data=await r.json();if(Array.isArray(data.providers)&&data.providers.length){sources=data.providers;
      const select=document.querySelector('#live-search-form [name=provider]');
      if(select){const selected=select.dataset.changed?select.value:select.dataset.preferredSource;select.innerHTML=options(sources.map(s=>[s.id,s.label]),selected);syncSourceFields();}}}}catch{}}
  loadSources();
  return {render,reset};
})();
