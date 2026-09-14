const test=require('node:test');
const assert=require('node:assert/strict');
const Store=require('../app/jobs-store.js');
const job=(id='1',extra={})=>({job_id:id,source:'linkedin',title:'Engineer',company:'Example',application_url:'https://www.linkedin.com/jobs/view/'+id,...extra});
test('Source identity stays stable and missing details stay unknown',()=>{
  const j=Store.normalize(job());
  assert.equal(j.id,'linkedin:1');assert.equal(j.workplace_type,null);assert.equal(j.salary,null);assert.deepEqual(j.skills,[]);
  const view=Store.present(j);assert.equal(view.employment,'');assert.equal(view.mode,'Work arrangement not listed');
  assert.notEqual(j.id,Store.normalize(job('1',{source:'other'})).id);
});
test('Reject unsafe or incomplete listings and keep source text as text',()=>{
  for(const url of ['javascript:alert(1)','https://name:password@example.com','not a url'])assert.equal(Store.normalize(job('1',{application_url:url})),null);
  assert.equal(Store.normalize(job('1',{title:''})),null);
  assert.equal(Store.normalize(job('1',{company:'<img src=x onerror=alert(1)>'})).company,'<img src=x onerror=alert(1)>');
});
test('A replacement search retains saved jobs and drops unrelated unsaved jobs',()=>{
  const old=[Store.normalize(job('1')),Store.normalize(job('2'))];
  const result=Store.merge(old,[job('3')],['linkedin:1']);
  assert.deepEqual(result.ids,['linkedin:3']);assert.deepEqual(result.jobs.map(j=>j.id),['linkedin:1','linkedin:3']);
});
test('Duplicate search results update a listing once',()=>{
  const result=Store.merge([], [job('1'),job('1',{title:'Updated title'})]);
  assert.equal(result.jobs.length,1);assert.equal(result.jobs[0].title,'Updated title');assert.deepEqual(result.ids,['linkedin:1']);
});
test('Descriptions supplied by the user survive source refresh and serialization',()=>{
  const old=Store.normalize(job('1',{description:'React and SQL',description_source:'pasted',skills:['React','SQL']}));
  const result=Store.merge([old],[job('1',{description:'A source update'})]);
  assert.equal(result.jobs[0].description,'React and SQL');assert.equal(result.jobs[0].description_source,'pasted');
  assert.deepEqual(Store.normalize(JSON.parse(JSON.stringify(result.jobs[0]))),result.jobs[0]);
});
test('Descriptions recognize literal skill names without partial-word matches',()=>{
  assert.deepEqual(Store.mentionedSkills('JavaScript and C++ plus PostgreSQL'),['JavaScript','C++','PostgreSQL']);
  assert.deepEqual(Store.mentionedSkills('We use React, SQL and My.Special[Tool]', ['My.Special[Tool]']),['React','SQL','My.Special[Tool]']);
});
test('Overlap uses the description and profile skills, not only source skill tags',()=>{
  const listing=Store.normalize(job('1',{description:'Build with React, SQL and a Custom Skill.',skills:['Excel']}));
  assert.deepEqual(Store.overlap(listing,['React','Custom Skill','Figma']),['React','Custom Skill']);
});
test('Related pipeline tools cover CI/CD and generic posting language is ignored',()=>{
  const listing=Store.normalize(job('1',{description:'Need Python, CI/CD, Communication, Kubernetes and PowerShell.'}));
  const profile=['Python','GitHub Actions','Jenkins Pipelines','GitLab CI/CD','Docker','Bash'];
  assert.deepEqual(Store.mentionedSkills(listing.description,profile).filter(s=>s==='Communication'),[]);
  assert.ok(Store.overlap(listing,profile).includes('CI/CD'));
  assert.ok(Store.overlap(listing,profile).includes('Python'));
  assert.equal(Store.overlap(listing,profile).includes('Kubernetes'),false);
  assert.equal(Store.overlap(listing,profile).includes('PowerShell'),false);
  const compared=Store.compareSkills(Store.mentionedSkills(listing.description,profile),profile);
  const ci=compared.matched.find(item=>item.name==='CI/CD');
  assert.ok(ci.via.some(name=>/github actions|jenkins|gitlab ci/i.test(name)));
  assert.ok(compared.missing.includes('Kubernetes'));
  assert.equal(compared.missing.includes('Communication'),false);
});
test('Sibling clouds are not treated as the same skill',()=>{
  const compared=Store.compareSkills(['AWS','Azure'],['AWS']);
  assert.deepEqual(compared.matched.map(item=>item.name),['AWS']);
  assert.deepEqual(compared.missing,['Azure']);
});

test('An umbrella skill cannot prove a named tool and aliases count once',()=>{
  assert.deepEqual(Store.compareSkills(['Jenkins','Docker','PostgreSQL'],['CI/CD','Containers','SQL']).matched,[]);
  assert.equal(Store.compareSkills(['Kubernetes','K8s'],['K8s']).matched.length,1);
  assert.equal(Store.compareSkills(['CI/CD'],['Jenkins']).matched.length,1);
  assert.equal(Store.compareSkills(['Azure'],['Azure DevOps']).matched.length,0);
  assert.equal(Store.mentionedSkills('Azure DevOps').includes('Azure'),false);
});
test('Translated descriptions are shown and still match original skill names',()=>{
  const listing=Store.normalize(job('1',{description:'Bouw diensten met Python en Ansible.',translated_description:'Build services with Python and Ansible.',source_language:'nl',translation_language:'en'}));
  assert.equal(Store.displayedDescription(listing),'Build services with Python and Ansible.');
  assert.deepEqual(Store.overlap(listing,['Python','Ansible']),['Python','Ansible']);
});
test('Easy Apply and company apply links stay on the listing',()=>{
  const easy=Store.normalize(job('1',{easy_apply:true}));
  assert.equal(easy.easy_apply,true);assert.equal(easy.external_apply_url,null);
  const company=Store.normalize(job('2',{easy_apply:false,external_apply_url:'https://careers.example.com/jobs/9'}));
  assert.equal(company.easy_apply,false);assert.equal(company.external_apply_url,'https://careers.example.com/jobs/9');
  assert.equal(Store.normalize(job('3',{external_apply_url:'https://www.linkedin.com/jobs/apply/3'})).external_apply_url,null);
});
test('Descriptions also recognize infrastructure skill names from the listing',()=>{
  assert.deepEqual(Store.mentionedSkills('Azure, Terraform, Ansible and Grafana'),['Azure','Terraform','Ansible','Grafana']);
});
test('CV locations become city and country for LinkedIn search',()=>{
  assert.equal(Store.formatLocation({city:'Amsterdam',country:'NL',raw:'Amsterdam, NL'}),'Amsterdam, Netherlands');
  assert.equal(Store.formatLocation({city:'Amsterdam'}),'Amsterdam, Netherlands');
  assert.equal(Store.formatLocation({city:'Berlin',country:'Germany'}),'Berlin, Germany');
  assert.equal(Store.formatLocation('Amsterdam, Netherlands'),'Amsterdam, Netherlands');
});
