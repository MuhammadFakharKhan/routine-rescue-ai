import { updateVirtualHome2D } from './virtual-home-2d.js';

const el=id=>document.getElementById(id);
let visualEvidence={outcome:'OBSERVED',violations:[]};
async function request(path, payload) {
  const opt=payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
  const response=await fetch(path,opt); const data=await response.json();
  if(!response.ok) throw new Error(data.error||'Request failed'); return data;
}
function textNode(parent,tag,content,className){const e=document.createElement(tag);if(className)e.className=className;e.textContent=content;parent.append(e);return e;}
function renderDevices(s){const wrap=el('observed-devices');wrap.replaceChildren(); for(const [name,fields] of Object.entries(s)){
 const node=textNode(wrap,'div','','device');const left=textNode(node,'div',name.replaceAll('_',' ').replace(/\b\w/g,m=>m.toUpperCase()));textNode(left,'small','Simulated hardware');
 const value=Object.entries(fields).map(([field,current])=>`${field.replaceAll('_',' ')}: ${current===null?'Not set':String(current).toUpperCase()}`).join(' · ');textNode(node,'span',value,'value');}}
async function refresh(){const data=await request('/api/status');renderDevices(data.state);updateVirtualHome2D(data.state,visualEvidence,visualEvidence?.verified===true?visualEvidence:null);return data;}
function renderPreview(p){const box=el('preview_result');box.replaceChildren(); if(!p.matched){textNode(box,'div',p.message);return;}
 textNode(box,'strong',`${p.routine} — saved warranty`);
 el('coverage').textContent=`Promise audit: ${p.audit.coverage_percent}% of modeled outcomes detected; ${p.audit.survived} blind spots. This is not a real-world safety guarantee.`; const ul=document.createElement('ul');box.append(ul);p.steps.forEach(s=>textNode(ul,'li',`${s.operation} → ${s.target}.${s.field} = ${JSON.stringify(s.value)}${s.requires_approval?' (requires approval)':''}`));textNode(box,'div',`Forbidden operations: ${p.forbidden_operations.join(', ')}`);}
function renderReceipt(r){const wrap=el('receipt');wrap.replaceChildren();const badge=el('outcome');badge.textContent=r.outcome;badge.className='chip '+((r.outcome==='VERIFIED'||r.outcome==='RECOVERED')?'good':r.outcome==='UNVERIFIED'?'unknown':'bad');textNode(wrap,'p',`Observed outcome: ${r.outcome}. Safe automatic retries used: ${r.retries}.`,'metric');
  for(const e of r.events){const line=textNode(wrap,'div','','evt');textNode(line,'span',`${e.operation}${e.retry?' (retry)':''}`);textNode(line,'strong',`${e.ack} / ${e.readback}`);}
  if(r.violations.length){textNode(wrap,'p','Unmet or unverified promises:','receiptHead');r.violations.forEach(v=>textNode(wrap,'div',`${v.target}.${v.field}: expected ${JSON.stringify(v.expected)}, observed ${JSON.stringify(v.actual)}`,'violation'));} else {textNode(wrap,'p','Every declared postcondition was verified in the local simulator.','metric');}
  el('export').disabled=false;}
async function doWork(action){try{return await action()}catch(e){alert(e.message)}finally{await refresh().catch(()=>{})}}
el('preview').addEventListener('click',()=>doWork(async()=>renderPreview(await request('/api/preview',{utterance:el('command').value}))));
el('execute').addEventListener('click',()=>doWork(async()=>{const data=await request('/api/execute',{utterance:el('command').value,fault_mode:el('fault').value,approve_sensitive:el('approval').checked});visualEvidence=data.receipt;renderReceipt(data.receipt)}));
el('reset').addEventListener('click',()=>doWork(async()=>{await request('/api/reset',{});visualEvidence={outcome:'RESET',violations:[]};el('outcome').textContent='Reset';el('outcome').className='chip';el('receipt').textContent='Virtual devices reset. Ready for the next scenario.';}));
el('export').addEventListener('click',()=>doWork(async()=>{const scenario=await request('/api/incidents/latest');const file=new Blob([JSON.stringify(scenario,null,2)],{type:'application/json'});const url=URL.createObjectURL(file);const a=document.createElement('a');a.href=url;a.download='exported-incident-v2.json';a.click();URL.revokeObjectURL(url);}));
refresh().catch(e=>console.error(e));

for(const [id,phrase] of [['goodnight','good night'],['focus','focus mode'],['leaving','leaving home']]){el(id).addEventListener('click',()=>{el('command').value=phrase;doWork(async()=>renderPreview(await request('/api/preview',{utterance:phrase})))})}
el('recover').addEventListener('click',()=>doWork(async()=>{const report=await request('/api/recover',{approve_recovery:true});if(report.verified)visualEvidence={...report,outcome:'RECOVERED',violations:[]};const wrap=el('receipt');textNode(wrap,'p',report.verified?'Recovery verified by modeled postconditions and change scope.':'Recovery partial / not verified.',report.verified?'metric':'violation');textNode(wrap,'pre',JSON.stringify(report,null,2));}));

// Warranty Studio — an intentional constrained editor, never an arbitrary tool runner.
let studioCatalog=[], studioDraft=null;
const rowWrap=el('action_rows');
function addStudioRow(action='living-off',time='07:00'){
 const row=document.createElement('div');row.className='studio-action';
 const select=document.createElement('select');select.className='studio-action-select';
 studioCatalog.forEach(c=>{const opt=document.createElement('option');opt.value=c.id;opt.textContent=c.label;select.append(opt)});
 select.value=action;
 const when=document.createElement('input');when.className='studio-time';when.placeholder='HH:MM';when.value=time;when.maxLength=5;
 const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='Remove';remove.addEventListener('click',()=>row.remove());
 function update(){when.hidden=select.value!=='alarm-time'}select.addEventListener('change',update);update();
 row.append(select,when,remove);rowWrap.append(row);
}
function payloadFromStudio(){
 const actions=Array.from(document.querySelectorAll('.studio-action')).map(r=>{
  const id=r.querySelector('select').value;return id==='alarm-time'?{id,time:r.querySelector('.studio-time').value}:{id};
 });
 const unchanged_fields=Array.from(document.querySelectorAll('.guard-field:checked')).map(x=>x.value);
 return {routine_id:el('routine_id').value.trim().toLowerCase(),name:el('routine_name').value.trim(),
   aliases:el('routine_aliases').value.split(',').map(x=>x.trim().toLowerCase()).filter(Boolean),actions,unchanged_fields};
}
function showDraft(d){studioDraft=d.warranty;const out=el('builder_output');out.replaceChildren();
 textNode(out,'strong',`Promise mutation audit: ${d.audit.coverage_percent}% (${d.audit.killed}/${d.audit.mutants} modeled mutations detected)`);
 textNode(out,'p',`Safety drift: ${d.drift.verdict}. This metric does not certify physical safety.`);
 d.audit.findings.filter(f=>f.status==='SURVIVED').forEach(f=>textNode(out,'p',`Blind spot: ${f.target}.${f.field} (${f.kind})`,'violation'));
 d.drift.findings.filter(f=>f.severity==='CRITICAL').forEach(f=>textNode(out,'p',`Critical change: ${f.message}`,'violation'));
}
async function reloadWarranties(){
 const list=await request('/api/warranties');const select=el('load_warranty');const previous=select.value;
 select.replaceChildren();const none=document.createElement('option');none.value='';none.textContent='Create new warranty';select.append(none);
 for(const w of list){const opt=document.createElement('option');opt.value=w.routine_id;opt.textContent=w.name;select.append(opt)}
 select.value=previous;
}
function studioCatalogLookup(step){
 if(step.operation==='SET_ALARM')return {id:'alarm-time',time:step.value};
 const c=studioCatalog.find(c=>c.operation===step.operation&&c.target===step.target&&c.field===step.field&&c.value===step.value);
 return {id:c?.id||'living-off',time:'07:00'};
}
async function loadStudioRoutine(){
 const id=el('load_warranty').value;
 if(!id){studioDraft=null;el('routine_id').value='';el('routine_name').value='';el('routine_aliases').value='';rowWrap.replaceChildren();addStudioRow();return;}
 const w=await request('/api/warranties/item/'+encodeURIComponent(id));
 el('routine_id').value=w.routine_id;el('routine_name').value=w.name;el('routine_aliases').value=w.aliases.join(', ');
 rowWrap.replaceChildren();w.steps.forEach(s=>{const v=studioCatalogLookup(s);addStudioRow(v.id,v.time)});
 document.querySelectorAll('.guard-field').forEach(g=>{const [target,field]=g.value.split('.');g.checked=(w.unchanged_fields||[]).some(x=>x.target===target&&x.field===field)});
 el('ack_safety_drift').checked=false;
 const versions=await request('/api/warranties/versions/'+encodeURIComponent(id));
 el('version_history').textContent=`Version history: ${versions.length?versions.map(x=>'v'+x.version).join(', '):'factory preset (not edited yet)'}`;
 studioDraft=null;
}
el('add_action').addEventListener('click',()=>addStudioRow());
el('load_builder').addEventListener('click',()=>doWork(loadStudioRoutine));
el('draft_warranty').addEventListener('click',()=>doWork(async()=>showDraft(await request('/api/warranties/draft',payloadFromStudio()))));
el('save_warranty').addEventListener('click',()=>doWork(async()=>{
 const draft=await request('/api/warranties/draft',payloadFromStudio());showDraft(draft);
 if(draft.drift.verdict==='BREAKING'&&!el('ack_safety_drift').checked){throw Error('Critical safety drift! Review the red findings and explicitly confirm before saving.');}
 const saved=await request('/api/warranties/save',{warranty:draft.warranty,confirm_safety_drift:el('ack_safety_drift').checked});
 const out=el('builder_output');textNode(out,'p',`Saved ${saved.warranty.routine_id} as version ${saved.warranty.warranty_version}.`,'metric');
 await reloadWarranties();el('load_warranty').value=saved.warranty.routine_id;await loadStudioRoutine();
}));
(async()=>{
 try{
  const catalog=await request('/api/catalog');studioCatalog=catalog.actions;
  const guards=el('protected_fields');
  catalog.fields.forEach(k=>{const lbl=document.createElement('label');lbl.className='check';const input=document.createElement('input');input.type='checkbox';input.value=k;input.className='guard-field';textNode(lbl,'span',k.replaceAll('_',' '));lbl.prepend(input);guards.append(lbl)});
  addStudioRow();await reloadWarranties();
 }catch(e){el('builder_output').textContent='Builder initialization failed: '+e.message}
})();
