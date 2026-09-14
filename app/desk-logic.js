/* Pure scheduling and backup checks shared by the UI and regression tests. */
'use strict';
const DeskLogic=(()=>{
  const day=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  function schedule(progress,rating,now=new Date()){
    const date=day(now),previous=Number(progress.intervalDays)||0;
    // Repeated clicks on the same day must not accelerate the schedule.
    const baseline=progress.lastReviewed===date?(Number(progress.intervalBeforeReview)||0):previous;
    const interval=rating==='again'?1:rating==='effort'?3:Math.min(30,Math.max(7,baseline*2));
    const next=new Date(now);next.setDate(next.getDate()+interval);
    return {intervalDays:interval,intervalBeforeReview:baseline,lastReviewed:date,reviewOn:day(next),recall:rating};
  }
  function validateBackup(raw){
    if(!raw||typeof raw!=='object'||Array.isArray(raw)||![1,2].includes(raw.version)||!raw.profile||typeof raw.profile!=='object'||Array.isArray(raw.profile))throw Error('Choose an ATS Matcher workspace export (version 1 or 2).');
    if(raw.version===2&&(!Array.isArray(raw.jobs)||!raw.applications||typeof raw.applications!=='object'||Array.isArray(raw.applications)))throw Error('This backup is missing its jobs or application records.');
    if((raw.jobs?.length||0)>5000)throw Error('This backup contains more than 5,000 listings. Use a smaller export.');
    return raw;
  }
  function dueItems(workspace,date=day(new Date())){
    const result=[];
    for(const job of workspace.jobs){
      const a=workspace.applications[job.id];if(!a||a.status==='Closed')continue;
      if(a.followup&&a.followup<=date)result.push({job:job.id,title:`Follow up · ${job.title}`,detail:job.company,date:a.followup,action:'workspace'});
      for(const lesson of a.interviewPrep?.learning_plan?.lessons||[]){
        const p=a.practiceProgress?.[lesson.id];
        if(p?.reviewOn&&p.reviewOn<=date)result.push({job:job.id,skill:lesson.id,title:`Review ${lesson.skill}`,detail:`${job.company} · ${lesson.minutes} min`,date:p.reviewOn,action:'coaching-lesson'});
      }
    }
    return result.sort((a,b)=>a.date.localeCompare(b.date)||a.title.localeCompare(b.title));
  }
  return {schedule,validateBackup,dueItems};
})();
if(typeof module!=='undefined')module.exports=DeskLogic;
