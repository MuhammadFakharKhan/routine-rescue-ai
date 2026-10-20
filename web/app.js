const el=id=>document.getElementById(id);
async function request(path, payload) {
  const opt=payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
  const response=await fetch(path,opt); const data=await response.json();
  if(!response.ok) throw new Error(data.error||'Request failed'); return data;
}
function textNode(parent,tag,content,className){const e=document.createElement(tag);if(className)e.className=className;e.textContent=content;parent.append(e);return e;}
function renderDevices(s){const wrap=el('devices');wrap.replaceChildren(); for(const [name,fields] of Object.entries(s)){
 const node=textNode(wrap,'div','','device');const left=textNode(node,'div',name.replaceAll('_',' ').replace(/\b\w/g,m=>m.toUpperCase()));textNode(left,'small','Simulated hardware');const value=Object.values(fields)[0];textNode(node,'span',value===null?'Not set':String(value).toUpperCase(),'value');}}
async function refresh(){const data=await request('/api/status');renderDevices(data.state)}
function renderPreview(p){const box=el('preview_result');box.replaceChildren(); if(!p.matched){textNode(box,'div',p.message);return;}
 textNode(box,'strong',`${p.routine} — saved warranty`); const ul=document.createElement('ul');box.append(ul);p.steps.forEach(s=>textNode(ul,'li',`${s.operation} → ${s.target}.${s.field} = ${JSON.stringify(s.value)}${s.requires_approval?' (requires approval)':''}`));textNode(box,'div',`Forbidden operations: ${p.forbidden_operations.join(', ')}`);}
function renderReceipt(r){const wrap=el('receipt');wrap.replaceChildren();const badge=el('outcome');badge.textContent=r.outcome;badge.className='chip '+((r.outcome==='VERIFIED'||r.outcome==='RECOVERED')?'good':r.outcome==='UNVERIFIED'?'unknown':'bad');textNode(wrap,'p',`Observed outcome: ${r.outcome}. Safe automatic retries used: ${r.retries}.`,'metric');
  for(const e of r.events){const line=textNode(wrap,'div','','evt');textNode(line,'span',`${e.operation}${e.retry?' (retry)':''}`);textNode(line,'strong',`${e.ack} / ${e.readback}`);}
  if(r.violations.length){textNode(wrap,'p','Unmet or unverified promises:','receiptHead');r.violations.forEach(v=>textNode(wrap,'div',`${v.target}.${v.field}: expected ${JSON.stringify(v.expected)}, observed ${JSON.stringify(v.actual)}`,'violation'));} else {textNode(wrap,'p','Every declared postcondition was verified in the local simulator.','metric');}
  el('export').disabled=false;}
async function doWork(action){try{await action()}catch(e){alert(e.message)}finally{await refresh().catch(()=>{})}}
el('preview').addEventListener('click',()=>doWork(async()=>renderPreview(await request('/api/preview',{utterance:el('command').value}))));
el('execute').addEventListener('click',()=>doWork(async()=>{const data=await request('/api/execute',{utterance:el('command').value,fault_mode:el('fault').value,approve_sensitive:el('approval').checked});renderReceipt(data.receipt)}));
el('reset').addEventListener('click',()=>doWork(async()=>{await request('/api/reset',{});el('outcome').textContent='Reset';el('outcome').className='chip';el('receipt').textContent='Virtual devices reset. Ready for the next scenario.';}));
el('export').addEventListener('click',()=>doWork(async()=>{const scenario=await request('/api/exports/latest');const file=new Blob([JSON.stringify(scenario,null,2)],{type:'application/json'});const url=URL.createObjectURL(file);const a=document.createElement('a');a.href=url;a.download='exported-scenario.json';a.click();URL.revokeObjectURL(url);}));
refresh().catch(e=>console.error(e));
