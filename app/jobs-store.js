/* Shared job listing normalization. */
(function(root){
  'use strict';
  const string=(value,max=500)=>typeof value==='string'?value.trim().slice(0,max):'';
  const skills=value=>Array.isArray(value)?[...new Set(value.map(s=>string(s,80)).filter(Boolean))].slice(0,100):[];
  function safeUrl(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:'';}catch{return '';}}
  function externalApplyUrl(value){
    const url=safeUrl(value);if(!url)return null;
    try{const host=new URL(url).hostname.toLowerCase();if(host==='linkedin.com'||host.endsWith('.linkedin.com'))return null;}catch{return null;}
    return url;
  }
  function normalize(raw){
    if(!raw||typeof raw!=='object')return null;
    const source=string(raw.source,80),job_id=string(raw.job_id,200),title=string(raw.title,500),company=string(raw.company,500),application_url=safeUrl(raw.application_url);
    if(!source||!job_id||!title||!company||!application_url)return null;
    return {id:encodeURIComponent(source)+':'+encodeURIComponent(job_id),source,job_id,title,company,application_url,
      location:string(raw.location)||null,salary:string(raw.salary)||null,
      workplace_type:['on_site','remote','hybrid'].includes(raw.workplace_type)?raw.workplace_type:null,
      employment_type:['full_time','part_time','contract','temporary','volunteer','internship'].includes(raw.employment_type)?raw.employment_type:null,
      posted_at:string(raw.posted_at,80)||null,posted_relative:string(raw.posted_relative,80)||null,
      description:string(raw.description,20000)||null,translated_description:string(raw.translated_description,20000)||null,
      source_language:string(raw.source_language,12)||null,translation_language:string(raw.translation_language,12)||null,
      description_source:raw.description_source==='pasted'?'pasted':'source',skills:skills(raw.skills),
      matched_skills:skills(raw.matched_skills),match_score:Number.isFinite(raw.match_score)?Math.max(0,Math.min(1,Number(raw.match_score))):null,
      easy_apply:raw.easy_apply===true?true:raw.easy_apply===false?false:null,external_apply_url:externalApplyUrl(raw.external_apply_url)};
  }
  function present(job){return job?{...job,mark:job.company.slice(0,2),color:'sage',location:job.location||'Location not listed',salary:job.salary||'Salary not listed',mode:{on_site:'On-site',remote:'Remote',hybrid:'Hybrid'}[job.workplace_type]||'Work arrangement not listed',employment:job.employment_type?job.employment_type.replaceAll('_',' '):'',posted:job.posted_relative||job.posted_at||'',summary:job.translated_description||job.description||'',tasks:[]}:null;}
  function merge(existing,incoming,keepIds=[]){
    const keep=new Set(keepIds),catalog=new Map();
    for(const raw of existing){const j=normalize(raw);if(j)catalog.set(j.id,j);}
    const ids=[];
    for(const raw of incoming.slice(0,100)){
      const j=normalize(raw);if(!j)continue;
      const old=catalog.get(j.id);
      if(old?.description_source==='pasted'){j.description=old.description;j.description_source='pasted';j.skills=old.skills;j.translated_description=null;j.translation_language=null;}
      catalog.set(j.id,j);if(!ids.includes(j.id))ids.push(j.id);
    }
    const retained=new Set([...keep,...ids]);
    return {jobs:[...catalog.values()].filter(j=>retained.has(j.id)),ids};
  }
  const KNOWN_SKILLS=['React','TypeScript','JavaScript','CSS','HTML','SQL','Python','Excel','Docker','Figma','User research','Prototyping','Product strategy','Patient care','Nursing','Care planning','Java','AWS','Git','Node.js','Project management','Leadership','Customer service','Data analysis','C++','C#','Go','Rust','Kubernetes','PostgreSQL','FastAPI','Django','Flask','Linux','Azure','GCP','Terraform','Redis','GraphQL','MongoDB','Spark','Pandas','NumPy','Tableau','Power BI','Salesforce','SAP','Jira','Agile','Scrum','CI/CD','Machine learning','Ansible','Jenkins','Grafana','Prometheus','Bash','PowerShell','GitHub Actions','GitLab CI/CD','Jenkins Pipelines','K8s','Continuous Integration','Continuous Delivery'];
  const GENERIC_SKILLS=['Communication','Communications','Communication skills','Written communication','Verbal communication','Excellent communication','Teamwork','Team player','Collaboration','Collaborative','Interpersonal','Interpersonal skills','Problem solving','Problem-solving','Attention to detail','Time management','Self-motivated','Self motivated','Fast learner','Quick learner','Work ethic','Positive attitude','Multitasking','Multi-tasking','Organizational skills','Organisation skills'];
  const ALIASES=[['CI/CD','CICD','CI-CD','CI CD','Continuous Integration','Continuous Delivery','Continuous Deployment'],['Kubernetes','K8s'],['Jenkins','Jenkins Pipelines','Jenkins Pipeline','Jenkins CI'],['GitHub Actions','Github Actions','GH Actions'],['GitLab CI/CD','GitLab CI','Gitlab CI/CD','Gitlab CI'],['PostgreSQL','Postgres'],['Node.js','NodeJS'],['RHEL','Red Hat','Red Hat Enterprise Linux','Redhat'],['REST APIs','REST API','RESTful APIs','RESTful'],['AWS','Amazon Web Services'],['Azure','Microsoft Azure'],['GCP','Google Cloud','Google Cloud Platform'],['Agile','Agile (Scrum)','Agile Scrum']];
  const FAMILIES=[{umbrella:['CI/CD'],tools:['Jenkins','GitHub Actions','GitLab CI/CD','CircleCI','Bitbucket Pipelines','Azure DevOps','Azure Pipelines','Travis CI']},{umbrella:['Linux'],tools:['RHEL','Ubuntu','Debian','CentOS','Fedora']},{umbrella:['Git','Version Control'],tools:['GitHub','GitLab','Bitbucket']},{umbrella:['Containers','Containerization'],tools:['Docker']},{umbrella:['Monitoring','Observability','Metrics','Alerting'],tools:['Prometheus','Grafana']},{umbrella:['Logging'],tools:['Splunk','ELK','ELK Stack']},{umbrella:['Access Control','IAM','Identity and Access Management'],tools:['LDAP','Okta','CyberArk','SSO']},{umbrella:['SQL'],tools:['PostgreSQL','MySQL','SQL Server','SQLite','MariaDB']}];
  const skillKey=name=>String(name||'').toLowerCase().trim().replaceAll('&',' and ').replace(/[/_\-]+/g,' ').replace(/[^a-z0-9+.# ]+/g,'').replace(/\s+/g,' ').trim();
  const GENERIC_KEYS=new Set(GENERIC_SKILLS.map(skillKey));
  const isGeneric=name=>GENERIC_KEYS.has(skillKey(name));
  const tokenPattern=label=>new RegExp('(^|[^a-z0-9])'+label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'([^a-z0-9]|$)','i');
  const containsSkill=(haystack,needle)=>skillKey(haystack)===skillKey(needle)||tokenPattern(needle).test(skillKey(needle)==='azure'?haystack.replace(/\bAzure\s+(?:DevOps|Pipelines)\b/gi,''):haystack);
  const aliasCanonical=new Map();
  for(const group of ALIASES)for(const label of group)aliasCanonical.set(skillKey(label),group[0]);
  const canonicalSkill=name=>aliasCanonical.get(skillKey(name))||String(name||'').trim();
  const familyRole=new Map();
  const familyLabels=[];
  FAMILIES.forEach((family,index)=>{
    [['umbrella',family.umbrella],['tool',family.tools]].forEach(([role,labels])=>labels.forEach(label=>{
      familyLabels.push(label);
      const key=skillKey(canonicalSkill(label));
      if(!familyRole.has(key))familyRole.set(key,[index,role]);
    }));
  });
  const catalog=extra=>[...new Map([...KNOWN_SKILLS,...familyLabels,...ALIASES.flat(),...skills(extra)].filter(name=>name&&!isGeneric(name)).map(s=>[s.toLowerCase(),s])).values()];
  function mentionedSkills(body,extra=[]){return catalog(extra).filter(s=>containsSkill(body,s));}
  function familyCover(jobCanon,profileSkill){
    const job=familyRole.get(skillKey(canonicalSkill(jobCanon))),profile=familyRole.get(skillKey(canonicalSkill(profileSkill)));
    if(!job||!profile||job[0]!==profile[0])return [];
    if(job[1]==='umbrella')return [profileSkill];
    return [];
  }
  function coverage(jobSkill,profile){
    const jobCanon=canonicalSkill(jobSkill),jobKey=skillKey(jobCanon);
    const covered=[];let sameName=false;
    for(const item of profile){
      if(isGeneric(item))continue;
      if(skillKey(item)===skillKey(jobSkill)||skillKey(canonicalSkill(item))===jobKey){
        if(skillKey(item)===skillKey(jobSkill))sameName=true;
        else covered.push(item);
        continue;
      }
      if(containsSkill(item,jobSkill)||containsSkill(item,jobCanon)){covered.push(item);continue;}
      covered.push(...familyCover(jobCanon,item));
    }
    if(sameName)return [];
    if(!covered.length)return null;
    const best=new Map();
    for(const item of covered){
      const key=skillKey(canonicalSkill(item)),prev=best.get(key);
      if(!prev||item.length>prev.length)best.set(key,item);
    }
    return [...best.values()];
  }
  function compareSkills(found,profileSkills){
    const profile=skills(profileSkills);
    const matched=[],missing=[],seen=new Set();
    for(const skill of found){
      const name=string(skill,80),key=skillKey(canonicalSkill(name));if(!name||isGeneric(name)||seen.has(key))continue;
      seen.add(key);
      const via=coverage(name,profile);
      if(via===null)missing.push(name);else matched.push({name,via});
    }
    return {matched,missing};
  }
  const COUNTRIES={nl:'Netherlands',nld:'Netherlands',de:'Germany',deu:'Germany',be:'Belgium',fr:'France',gb:'United Kingdom',uk:'United Kingdom',ie:'Ireland',es:'Spain',it:'Italy',pt:'Portugal',at:'Austria',ch:'Switzerland',se:'Sweden',no:'Norway',dk:'Denmark',fi:'Finland',pl:'Poland',cz:'Czechia',hu:'Hungary',us:'United States',usa:'United States',ca:'Canada',au:'Australia',in:'India',jp:'Japan',kr:'South Korea',sg:'Singapore',ae:'United Arab Emirates'};
  const CITY_COUNTRY={amsterdam:'Netherlands',rotterdam:'Netherlands',utrecht:'Netherlands',eindhoven:'Netherlands','the hague':'Netherlands','den haag':'Netherlands',berlin:'Germany',munich:'Germany',hamburg:'Germany',frankfurt:'Germany',cologne:'Germany',vienna:'Austria',brussels:'Belgium',zurich:'Switzerland',copenhagen:'Denmark',stockholm:'Sweden',oslo:'Norway',helsinki:'Finland',dublin:'Ireland',lisbon:'Portugal',madrid:'Spain',barcelona:'Spain',rome:'Italy',milan:'Italy',warsaw:'Poland',prague:'Czechia',london:'United Kingdom',manchester:'United Kingdom',paris:'France','new york':'United States','san francisco':'United States',seattle:'United States',toronto:'Canada',sydney:'Australia',singapore:'Singapore',bangalore:'India',bengaluru:'India',dubai:'United Arab Emirates'};
  function expandCountry(value){
    const text=string(value,80);if(!text)return '';
    return COUNTRIES[text.toLowerCase().replaceAll('.','')]||text;
  }
  function formatLocation(value){
    if(typeof value==='string')return string(value,100);
    if(!value||typeof value!=='object')return '';
    const city=string(value.city,80);
    const country=expandCountry(value.country)||CITY_COUNTRY[city.toLowerCase()]||'';
    if(city&&country&&!city.toLowerCase().includes(country.toLowerCase())&&!country.toLowerCase().includes(city.toLowerCase()))return string(`${city}, ${country}`,100);
    return city||country||string(value.raw,100);
  }
  function displayedDescription(job){return job&&(job.translated_description||job.description)||'';}
  function overlap(job,profileSkills){
    const extras=skills(profileSkills);
    const body=[job.translated_description,job.description].filter(Boolean).join('\n');
    const found=body?mentionedSkills(body,extras):skills(job.skills);
    return compareSkills(found,extras).matched.map(item=>item.name);
  }
  const api={normalize,present,merge,safeUrl,mentionedSkills,compareSkills,formatLocation,overlap,displayedDescription};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.JobStore=api;
})(globalThis);
