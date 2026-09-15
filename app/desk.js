/* Application workflows and workspace recovery. Render user content as plain text. */
'use strict';
const Desk=(()=>{
  let pendingBackup=null,backupEpoch=0,revision=null;
  const limit=(value,n)=>typeof value==='string'?value.slice(0,n):'';
  function nextActions(){
    const due=DeskLogic.dueItems(state),drafts=state.jobs.filter(j=>state.applications[j.id]?.status==='Saved'&&state.applications[j.id]?.coverDraft?.trim());
    if(!due.length&&!drafts.length)return '';
    const items=[...due,...drafts.map(j=>({job:j.id,title:`Continue your letter · ${j.title}`,detail:j.company,action:'cover-letter'}))].slice(0,5);
    return `<section class="desk-agenda"><div class="section-title"><h2>Pick up where you left off</h2><span class="tag">${due.length} due</span></div>${items.map(i=>`<article><div><strong>${esc(i.title)}</strong><p>${esc(i.detail)}${i.date?` · ${esc(i.date)}`:''}</p></div><button class="button secondary small" data-action="${i.action}" data-id="${esc(i.job)}" ${i.skill?`data-skill="${esc(i.skill)}"`:''}>Open →</button></article>`).join('')}</section>`;
  }
  function showRestore(){
    pendingBackup=null;backupEpoch++;
    openModal(`<h2 id="modal-title">Bring your workspace back.</h2><p class="modal-description">Choose a workspace JSON export. Review its contents before replacing the current workspace. Your current workspace is kept as a recovery copy on this device.</p><label class="field">Workspace backup<input id="workspace-backup" type="file" accept=".json,application/json"></label><div id="backup-preview" role="status"></div>`,'WORKSPACE / RESTORE');
  }
  async function previewBackup(file){
    const epoch=++backupEpoch,target=document.getElementById('backup-preview');pendingBackup=null;if(!file||!target)return;
    try{
      if(file.size>10*1024*1024)throw Error('Choose a backup smaller than 10 MB.');
      const raw=DeskLogic.validateBackup(JSON.parse(await file.text()));
      if(epoch!==backupEpoch||!target.isConnected||!modal.open)return;
      const restored=readWorkspace(raw);
      if(raw.version===2&&(restored.jobs.length!==raw.jobs.length||Object.keys(restored.applications).length!==Object.keys(raw.applications).length))throw Error('Some listings or application records are invalid or duplicated. This backup cannot be restored without losing records. Your workspace is unchanged.');
      pendingBackup={state:restored,previous:state};
      target.innerHTML=`<div class="notice"><strong>${esc(restored.profile.name||'Unnamed profile')}</strong><p>${restored.jobs.length} listings · ${Object.keys(restored.applications).length} applications · ${restored.versions.length} saved versions</p>${raw.version===1?'<p>This older export will be kept in the Earlier browser save archive.</p>':''}<p>Restoring replaces the current workspace. It does not combine two profiles.</p></div><div class="button-row"><button class="button" data-action="desk-confirm-restore">Restore this workspace</button><button class="button secondary" data-action="export">Download my current workspace first</button></div>`;
    }catch(error){if(epoch===backupEpoch&&target.isConnected)target.textContent=error instanceof SyntaxError?'This file is not valid JSON. Your workspace is unchanged.':error.message;}
  }
  function replaceWorkspace(next){
    const previous=JSON.stringify(state),serialized=JSON.stringify(next);
    // Keep both writes before mutating memory. A quota error leaves the active workspace intact.
    localStorage.setItem(KEY+':before-restore',previous);
    localStorage.setItem(KEY,serialized);
    Coaching.cancel();searchEpoch++;importEpoch++;LiveSearch.reset();shortlistLoading=false;shortlistError='';
    state=next;activeFilter='All';searchTerm='';pendingBackup=null;closeModal();navigate('today');save();
  }
  function restoreBackup(){
    if(!pendingBackup||pendingBackup.previous!==state||!document.getElementById('backup-preview'))return;
    try{replaceWorkspace(pendingBackup.state);notify('Workspace restored. The previous workspace is available in My profile.');}
    catch{notify('There is not enough browser storage to keep both workspaces. Export your current workspace before freeing browser storage. Nothing was replaced.');}
  }
  function downloadRecovery(){try{const body=localStorage.getItem(KEY+':before-restore');if(body){download('workspace-before-restore.json',body,'application/json');return;}}catch{}notify('No recovery copy is available yet.');}
  function showAddJob(){
    openModal(`<h2 id="modal-title">Bring a role you found elsewhere.</h2><p class="modal-description">Paste a listing from a company website, another job board, or a recruiter. This saves a local copy for letters, comparison, and practice.</p><form id="desk-job-form"><div class="form-grid"><label class="field">Job title<input name="title" required maxlength="200"></label><label class="field">Company<input name="company" required maxlength="200"></label><label class="field full">Original listing link<input name="url" type="url" required maxlength="2000" placeholder="https://…"></label><label class="field">Location<input name="location" maxlength="200"></label><label class="field">Work arrangement<select name="workplace_type"><option value="">Not specified</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="on_site">On-site</option></select></label><label class="field full">Full job description<textarea name="description" required minlength="40" maxlength="12000" rows="8"></textarea><small>Paste the requirements and responsibilities. The app does not fetch this link.</small></label></div><p id="manual-job-error" role="alert"></p><button class="button" type="submit">Save this opportunity →</button></form>`,'APPLICATION / ADD A ROLE');
  }
  function addJob(form){
    const f=new FormData(form),url=JobStore.safeUrl(f.get('url')),error=document.getElementById('manual-job-error');
    if(!url){error.textContent='Use a complete http or https listing link without embedded credentials.';return;}
    const canonical=link=>{const u=new URL(link);u.hash='';for(const key of [...u.searchParams.keys()])if(key.startsWith('utm_'))u.searchParams.delete(key);return u.href;};
    const existing=state.jobs.find(j=>canonical(j.application_url)===canonical(url));
    if(existing){ensureSaved(existing.id);save();showWorkspace(existing.id);notify('This listing is already in your workspace. Your existing notes and drafts are kept.');return;}
    const job=JobStore.normalize({source:'manual',job_id:crypto.randomUUID(),title:String(f.get('title')||''),company:String(f.get('company')||''),application_url:url,location:String(f.get('location')||''),workplace_type:f.get('workplace_type'),description:String(f.get('description')||''),description_source:'pasted'});
    if(!job||job.description.length<40){error.textContent='Add a title, company, and at least 40 characters of the job description.';return;}
    job.skills=JobStore.mentionedSkills(job.description,state.profile.skills);state.jobs.push(job);ensureSaved(job.id);recordAction(`save:${job.id}`);save();closeModal();navigate('applications');showWorkspace(job.id);notify('Opportunity saved. Compare it with your profile or start a letter.');
  }
  async function showEvidence(id){
    Coaching.captureLetter(id);ensureSaved(id);
    openModal('<h2 id="modal-title">Find an example worth telling.</h2><p role="status">Reading this role’s requirements…</p>','LETTER / EVIDENCE');
    try{
      const result=await Coaching.request('/api/role-analysis',id);if(!result)return;
      const context=Coaching.readContext(result.data),a=state.applications[id];
      const topics=(context?.requirements||[]).filter(r=>r.status==='not_evidenced'&&!r.alternative_covered).slice(0,3);
      openModal(`<h2 id="modal-title">Give your letter a real example.</h2><p class="modal-description">${esc(jobById(id).title)} · ${esc(jobById(id).company)}. Skip anything you cannot support.</p>${topics.length?`<div class="notice">The listing mentions ${topics.map(r=>esc(r.name)).join(', ')} without clear evidence in your profile. Have you used any of these at work, in study, or in a personal project? Missing CV evidence does not mean you lack the skill.</div>`:''}<form id="desk-evidence-form" data-job="${esc(id)}"><label class="field">What was the setting?<textarea name="setting" maxlength="350" rows="2" placeholder="Was this paid work, study, volunteering, or a personal project?"></textarea></label><label class="field field-row">What did you personally do?<textarea name="action" maxlength="650" rows="3" placeholder="Name the tools, decisions, or conversations that were actually yours."></textarea></label><label class="field field-row">What happened, or what did you learn?<textarea name="outcome" maxlength="350" rows="2" placeholder="Leave blank if unknown. Include numbers only when supported."></textarea></label><label class="checkbox-field"><input name="confirmed" type="checkbox"><span>This describes my real experience. Save it with my profile for future applications.</span></label><label class="field field-row">What interests you about this specific role?<textarea name="motivation" maxlength="800" rows="3">${esc(a.motivation||'')}</textarea><small>Saved for this application as your motivation, separate from career evidence.</small></label><div id="evidence-error" role="alert"></div><div class="button-row"><button class="button" type="submit">Save and return to my letter</button><button class="button secondary" type="button" data-action="cover-letter" data-id="${esc(id)}">Skip for now</button></div></form>`,'LETTER / EVIDENCE');
    }catch(error){Coaching.showLetter(id,'',error.message);}
  }
  function saveEvidence(form){
    const a=state.applications[form.dataset.job];if(!a)return;
    const fields=new FormData(form),setting=String(fields.get('setting')||'').trim(),action=String(fields.get('action')||'').trim(),outcome=String(fields.get('outcome')||'').trim();
    const error=document.getElementById('evidence-error');
    if((setting||action||outcome)&&(!setting||!action||fields.get('confirmed')!=='on')){error.textContent='Add the setting and your own action, then confirm this is real experience. You can also leave all three example fields blank.';return;}
    const example=[setting,action,outcome].filter(Boolean).join('\n'),existing=state.profile.background.achievements||'';
    const combined=example&&!existing.includes(example)?[existing,example].filter(Boolean).join('\n\n'):existing;
    if(combined.length>3000){error.textContent='Your examples are full. Shorten this example or edit existing examples in My profile before adding more. Nothing has been removed.';return;}
    state.profile.background.achievements=combined;a.motivation=limit(String(fields.get('motivation')||''),800);a.coverReview=null;
    persist();Coaching.showLetter(form.dataset.job);notify('Your confirmed evidence and motivation are saved.');
  }
  function rewriteControls(id,ready){return `<div class="passage-tools"><label class="field">Revise selected text<select id="passage-intent"><option value="plain">Use simpler language</option><option value="specific">Connect it to this role</option><option value="shorten">Make it shorter</option></select></label><button class="button secondary" data-action="desk-revise" data-id="${esc(id)}" ${ready?'':'disabled'}>Suggest an edit →</button><p class="tiny-note">Select 20–2,000 characters in the letter. You’ll review the change before applying it.</p></div>`;}
  async function revise(id){
    const editor=document.getElementById('cover-letter-text');if(!editor)return;
    const start=editor.selectionStart,end=editor.selectionEnd,letter=editor.value,selected=letter.slice(start,end);
    if(selected.trim().length<20||selected.length>2000){notify('Select 20–2,000 characters in your letter first.');return;}
    Coaching.captureLetter(id);const options=Coaching.readOptions(state.applications[id].letterOptions),instruction=document.getElementById('passage-intent').value;
    revision=null;
    openModal('<h2 id="modal-title">Revising your selected passage.</h2><p class="notice" role="status">Your complete draft is saved. The suggestion will appear beside the original for your review.</p>','LETTER / EDIT');
    try{
      const result=await Coaching.request('/api/cover-letter-revise',id,{letter,start:[...letter.slice(0,start)].length,end:[...letter.slice(0,end)].length,instruction,options});if(!result)return;
      const replacement=limit(result.data.replacement,2500);if(!replacement.trim())throw Error('No usable revision was returned.');
      revision={id,start,end,letter,replacement,source:result.source,application:state.applications[id],review:result.data.review};
      openModal(`<h2 id="modal-title">Does this sound like you?</h2><div class="revision-grid"><section><h3>Your original</h3><pre>${esc(selected)}</pre></section><section><h3>Suggested edit</h3><pre>${esc(replacement)}</pre></section></div><p class="tiny-note">Review the facts and wording. Automatic checks cannot verify every claim. Only this selection will change.</p><div class="button-row"><button class="button" data-action="desk-accept-revision" data-id="${esc(id)}">Use this edit</button><button class="button secondary" data-action="cover-letter" data-id="${esc(id)}">Keep my original</button></div>`,'LETTER / REVIEW');
    }catch(error){Coaching.showLetter(id,'',error.message);}
  }
  function acceptRevision(id){
    const r=revision,a=state.applications[id];
    if(!r||r.id!==id||a!==r.application||a.coverDraft!==r.letter||r.source!==Coaching.sourceKey(id)){notify('The draft or evidence changed. Request a fresh revision.');return;}
    Coaching.saveDraftVersion(id,r.letter,'Before revising a passage');
    a.coverDraft=r.letter.slice(0,r.start)+r.replacement+r.letter.slice(r.end);a.coverReview=Coaching.readReview(r.review);a.coverSource=r.source;
    revision=null;persist();Coaching.showLetter(id);notify('Selected passage updated. Your previous draft is saved in Application drafts.');
  }
  function diagnosticMarkup(id,lesson,p){
    if(lesson.kind==='soft')return '';
    return `<details class="evidence-panel"><summary>Find my starting level</summary><p>Answer the warm-up above before reading the notes. Then check what you can do without help.</p>${[['explain','I can explain the idea in my own words.'],['apply','I can work through a small example.'],['debug','I can explain an edge case or diagnose a failure.']].map(([key,label])=>`<label class="checkbox-field"><input type="checkbox" data-diagnostic="${key}" ${p.diagnostic?.[key]?'checked':''}><span>${label}</span></label>`).join('')}<p class="tiny-note">Your own assessment guides the starting level. You can always switch it later.</p><button type="button" class="button secondary" data-action="desk-level" data-id="${esc(id)}" data-skill="${lesson.id}">Use my starting level</button></details>`;
  }
  function recallMarkup(p){return `<label class="field field-row">How much help did you need?<select data-practice-field="recall"><option value="again" ${p.recall==='again'||!p.recall?'selected':''}>I need another attempt · review tomorrow</option><option value="effort" ${p.recall==='effort'?'selected':''}>I managed with some help · review in 3 days</option><option value="independent" ${p.recall==='independent'?'selected':''}>I managed independently · extend my review interval</option></select><small>Your self-report sets a reminder in this workspace; it does not certify proficiency.</small></label>`;}
  document.addEventListener('click',event=>{
    const b=event.target.closest('[data-action]');if(!b||b.disabled)return;const id=b.dataset.id;
    const handlers={'desk-add-job':showAddJob,'desk-restore':showRestore,'desk-confirm-restore':restoreBackup,'desk-recovery':downloadRecovery,'desk-evidence':()=>showEvidence(id),'desk-revise':()=>revise(id),'desk-accept-revision':()=>acceptRevision(id),'desk-level':()=>{
      const p=state.applications[id]?.practiceProgress?.[b.dataset.skill];
      if(!p?.warmup?.trim()){notify('Answer the warm-up first, then assess what you can do.');return;}
      const mode=p.diagnostic?.explain&&p.diagnostic?.apply?'refresher':'foundation';
      Coaching.adaptLesson(id,b.dataset.skill,mode,false);
    }};
    handlers[b.dataset.action]?.();
  });
  document.addEventListener('change',event=>{
    if(event.target.id==='workspace-backup')previewBackup(event.target.files[0]);
    if(event.target.dataset.diagnostic){const form=event.target.closest('.lesson-work'),p=state.applications[form?.dataset.job]?.practiceProgress?.[form?.dataset.skill];if(p){p.diagnostic={...p.diagnostic,[event.target.dataset.diagnostic]:event.target.checked};persist();}}
  });
  document.addEventListener('submit',event=>{
    if(event.target.id==='desk-evidence-form'){event.preventDefault();saveEvidence(event.target);}
    if(event.target.id==='desk-job-form'){event.preventDefault();addJob(event.target);}
  });
  return {nextActions,showRestore,previewBackup,rewriteControls,diagnosticMarkup,recallMarkup};
})();
