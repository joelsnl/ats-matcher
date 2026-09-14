const {test}=require('node:test');
const assert=require('node:assert/strict');
const {schedule,validateBackup,dueItems}=require('../app/desk-logic.js');
test('review intervals reflect recall, use local calendar dates, and cap at 30 days',()=>{
  const now=new Date(2026,0,31,23,30);
  assert.equal(schedule({},'again',now).reviewOn,'2026-02-01');
  assert.equal(schedule({},'effort',now).reviewOn,'2026-02-03');
  assert.equal(schedule({},'independent',now).intervalDays,7);
  assert.equal(schedule({intervalDays:21},'independent',now).intervalDays,30);
});
test('repeated same-day completion does not inflate review intervals',()=>{
  const now=new Date(2026,8,14),first=schedule({intervalDays:7},'independent',now);
  assert.equal(first.intervalDays,14);
  assert.equal(schedule(first,'independent',now).intervalDays,14);
  assert.equal(schedule(first,'again',now).intervalDays,1);
  assert.equal(schedule(first,'independent',new Date(2026,8,28)).intervalDays,28);
});
test('due queue includes overdue reviews and followups, excludes future and closed applications',()=>{
  const workspace={jobs:[{id:'a',title:'Engineer',company:'A'},{id:'b',title:'Engineer',company:'B'}],applications:{a:{status:'Interview',followup:'2026-09-15',interviewPrep:{learning_plan:{lessons:[{id:'s',skill:'SQL',minutes:20}]}},practiceProgress:{s:{reviewOn:'2026-09-12'}}},b:{status:'Closed',followup:'2026-01-01'}}};
  assert.deepEqual(dueItems(workspace,'2026-09-14').map(i=>i.action),['coaching-lesson']);
  assert.equal(dueItems(workspace,'2026-09-15').length,2);
});
test('restore rejects unrelated, unsupported and incomplete documents',()=>{
  for(const raw of [null,[],{version:3,profile:{}},{version:2,profile:[]},{version:2,profile:{},jobs:[]}])assert.throws(()=>validateBackup(raw));
  assert.throws(()=>validateBackup({version:2,profile:{},jobs:Array(5001),applications:{}}));
  assert.equal(validateBackup({version:1,profile:{}}).version,1);
  assert.equal(validateBackup({version:2,profile:{},jobs:[],applications:{}}).version,2);
});
