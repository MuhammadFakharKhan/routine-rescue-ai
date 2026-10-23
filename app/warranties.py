"""Constrained, versioned editor for SIMULATED local routines; no arbitrary code or URLs.

Security design: only known simulated operation/target/field triples may be edited.
Locking always requires human approval; unlocking is never offered. Existing
contracts are kept as immutable version snapshots in SQLite.
"""
import copy
import json
import re
import time
from .assurance import compare_warranties, audit_warranty

CATALOG = (
    {'id':'living-on','label':'Living-room lights on','operation':'LIGHT_ON','target':'living_light','field':'power','value':'on'},
    {'id':'living-off','label':'Living-room lights off','operation':'LIGHT_OFF','target':'living_light','field':'power','value':'off'},
    {'id':'desk-on','label':'Desk light on','operation':'LIGHT_ON','target':'desk_light','field':'power','value':'on'},
    {'id':'desk-off','label':'Desk light off','operation':'LIGHT_OFF','target':'desk_light','field':'power','value':'off'},
    {'id':'ambient-on','label':'Ambient light on','operation':'LIGHT_ON','target':'ambient_light','field':'power','value':'on'},
    {'id':'ambient-off','label':'Ambient light off','operation':'LIGHT_OFF','target':'ambient_light','field':'power','value':'off'},
    {'id':'lock-door','label':'Lock the door (approval required)','operation':'LOCK','target':'front_door','field':'locked','value':True},
    {'id':'alarm-time','label':'Set alarm (HH:MM)','operation':'SET_ALARM','target':'alarm','field':'time','value':'07:00'},
)

KNOWN_FIELDS = {('living_light','power'),('desk_light','power'),('ambient_light','power'),('front_door','locked'),('alarm','time')}

def validate(w):
    if not isinstance(w,dict): raise ValueError('Warranty must be an object')
    required={'schema_version','warranty_id','routine_id','name','aliases','steps','postconditions','forbidden_operations','recovery','verification'}
    optional={'invariants','warranty_version','side_effect_candidates','unchanged_fields'}
    if set(w)-required-optional or required-set(w):raise ValueError('Missing or unsupported warranty fields')
    if w['schema_version']!='1.0.0':raise ValueError('Unsupported warranty schema')
    if not isinstance(w['routine_id'],str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,39}',w['routine_id']):raise ValueError('routine_id must be a short kebab-case identifier')
    if w['warranty_id'] != w['routine_id']+'-warranty':raise ValueError('warranty_id must be routine_id + "-warranty"')
    if not isinstance(w['name'],str) or not 2<=len(w['name'].strip())<=80:raise ValueError('Routine name length must be 2–80')
    if not isinstance(w['aliases'],list) or not 1<=len(w['aliases'])<=8:raise ValueError('Provide 1–8 trigger phrases')
    aliases=[]
    for value in w['aliases']:
        if not isinstance(value,str) or not 2<=len(value.strip())<=80:raise ValueError('Invalid trigger phrase')
        aliases.append(' '.join(value.strip().lower().split()))
    if len(set(aliases))!=len(aliases):raise ValueError('Duplicate aliases')
    if not isinstance(w['steps'],list) or not 1<=len(w['steps'])<=10:raise ValueError('Provide 1–10 steps')
    known_ops={('LOCK','front_door','locked',True),('LIGHT_ON','living_light','power','on'),('LIGHT_OFF','living_light','power','off'),
       ('LIGHT_ON','desk_light','power','on'),('LIGHT_OFF','desk_light','power','off'),('LIGHT_ON','ambient_light','power','on'),('LIGHT_OFF','ambient_light','power','off')}
    used=set()
    for s in w['steps']:
        if not isinstance(s,dict) or set(s)!={'step_id','operation','target','field','value','risk','requires_approval'}:raise ValueError('Invalid step shape')
        if not isinstance(s['step_id'],str) or not re.fullmatch(r'[a-z0-9-]{2,50}',s['step_id']) or s['step_id'] in used:raise ValueError('Duplicate/invalid step ID')
        used.add(s['step_id'])
        spec=(s['operation'],s['target'],s['field'],s['value'])
        if s['operation']=='SET_ALARM':
            if not (s['target']=='alarm' and s['field']=='time' and isinstance(s['value'],str) and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',s['value'])):raise ValueError('Alarm time must be HH:MM')
        elif spec not in known_ops:raise ValueError('Unsupported or unsafe simulated operation/target/value combination')
        if s['operation']=='LOCK':
            if s['risk']!='sensitive' or s['requires_approval'] is not True:raise ValueError('Door lock must require explicit approval')
        elif s['risk']!='low' or s['requires_approval'] is not False:raise ValueError('Non-lock steps must use low risk policy')
    if not isinstance(w['postconditions'],list) or len(w['postconditions'])<1:raise ValueError('Postconditions missing')
    if not isinstance(w['forbidden_operations'],list) or 'UNLOCK' not in w['forbidden_operations']:raise ValueError('UNLOCK must remain forbidden')
    if len(set(w['forbidden_operations']))!=len(w['forbidden_operations']):raise ValueError('Duplicate forbidden operations')
    if any(x not in {'UNLOCK','LOCK','LIGHT_ON','LIGHT_OFF','SET_ALARM'} for x in w['forbidden_operations']):raise ValueError('Invalid forbidden operation')
    rr=w['recovery']; v=w['verification']
    if not isinstance(rr,dict) or set(rr)!={'auto_retry_operations','max_auto_retries','sensitive_retry_requires_approval'} or rr['max_auto_retries'] not in (0,1) or rr['sensitive_retry_requires_approval'] is not True:raise ValueError('Unsafe recovery policy')
    if not isinstance(rr['auto_retry_operations'],list) or any(x not in ('LIGHT_ON','LIGHT_OFF') for x in rr['auto_retry_operations']):raise ValueError('Only low-risk lights may auto retry')
    if v!={'require_readback':True,'unknown_is_success':False}:raise ValueError('Independent readback must remain enforced')
    for label in ('postconditions','invariants'):
        for p in w.get(label,[]):
            if not isinstance(p,dict) or set(p)!={'target','field','equals'} or (p['target'],p['field']) not in KNOWN_FIELDS:raise ValueError('Unsupported assertion')
    for label in ('side_effect_candidates','unchanged_fields'):
        rows=w.get(label,[])
        if not isinstance(rows,list) or len(rows)>20:raise ValueError('Invalid protected side-effects')
        for p in rows:
            keys={'target','field','baseline'} if label=='side_effect_candidates' else {'target','field'}
            if not isinstance(p,dict) or set(p)!=keys or (p['target'],p['field']) not in KNOWN_FIELDS:raise ValueError('Unknown protected side-effect field')
    action_fields={(s['target'],s['field']) for s in w['steps']}
    for row in w.get('unchanged_fields',[]):
        if (row['target'],row['field']) in action_fields:raise ValueError('Unchanged guard cannot target a field the routine deliberately changes')
    for p in w['postconditions']:
        if (p['target'],p['field']) not in action_fields:raise ValueError('Each postcondition must match a declared step field')
        if not any((s['target'],s['field'],s['value'])==(p['target'],p['field'],p['equals']) for s in w['steps']):raise ValueError('Postcondition conflicts with step')
    postkeys={(p['target'],p['field']) for p in w['postconditions']}
    if action_fields-postkeys:raise ValueError('Every action must have an expected postcondition')
    for p in w.get('side_effect_candidates',[]):
        if (p['target'],p['field']) in action_fields:raise ValueError('Side-effect candidates must differ from routine action fields')
    return copy.deepcopy(w)

def draft(payload, initial_state):
    if not isinstance(payload,dict): raise ValueError('Builder input must be an object')
    if set(payload)-{'routine_id','name','aliases','actions','unchanged_fields'}:raise ValueError('Unexpected builder field')
    rid=payload.get('routine_id'); name=payload.get('name'); aliases=payload.get('aliases'); actions=payload.get('actions')
    if not isinstance(actions,list) or not 1<=len(actions)<=10:raise ValueError('Select between 1 and 10 actions')
    catalog={x['id']:x for x in CATALOG}; steps=[]; post=[]; seen=set()
    for index,item in enumerate(actions):
        if not isinstance(item,dict) or set(item)-{'id','time'}:raise ValueError('Invalid action')
        spec=catalog.get(item.get('id'))
        if spec is None:raise ValueError('Unsupported simulated action')
        value=item.get('time','07:00') if spec['id']=='alarm-time' else spec['value']
        if spec['id']!='alarm-time' and 'time' in item:raise ValueError('Time is only valid for SET_ALARM')
        key=(spec['target'],spec['field'])
        if key in seen:raise ValueError('Each target field can be changed only once per routine')
        seen.add(key)
        steps.append({'step_id':f'action-{index+1}', 'operation':spec['operation'],'target':spec['target'],'field':spec['field'],
                      'value':value,'risk':'sensitive' if spec['operation']=='LOCK' else 'low','requires_approval':spec['operation']=='LOCK'})
        post.append({'target':spec['target'],'field':spec['field'],'equals':value})
    guards=payload.get('unchanged_fields',[])
    if not isinstance(guards,list):raise ValueError('unchanged_fields must be an array')
    unchanged=[]; candidates=[]
    for key in guards:
        if not isinstance(key,str) or '.' not in key:raise ValueError('Invalid protected field')
        target,field=key.split('.',1)
        if (target,field) not in KNOWN_FIELDS or (target,field) in seen:raise ValueError('Protected field must exist and be untouched by routine')
        if {'target':target,'field':field} in unchanged:continue
        unchanged.append({'target':target,'field':field})
        candidates.append({'target':target,'field':field,'baseline':initial_state.get(target,{}).get(field)})
    w={'schema_version':'1.0.0','warranty_id':str(rid)+'-warranty','routine_id':rid,'name':name,'aliases':aliases,
       'steps':steps,'postconditions':post,'invariants':[], 'side_effect_candidates':candidates,'unchanged_fields':unchanged,
       'forbidden_operations':['UNLOCK'], 'recovery':{'auto_retry_operations':['LIGHT_ON','LIGHT_OFF'],'max_auto_retries':1,'sensitive_retry_requires_approval':True},
       'verification':{'require_readback':True,'unknown_is_success':False},'warranty_version':'1.0.0'}
    return validate(w)

def save_version(db,w,defaults,confirm_breaking=False,universe=None):
    w=validate(w)
    row=db.execute('SELECT version,json FROM warranty_versions WHERE routine_id=? ORDER BY version DESC LIMIT 1',(w['routine_id'],)).fetchone()
    old=json.loads(row[1]) if row else defaults.get(w['routine_id'])
    # Existing factory warranties are version-zero; preserving factory source as an immutable version.
    if row is None and old is not None:
        db.execute('INSERT INTO warranty_versions(routine_id,version,created_at,json) VALUES(?,?,?,?)',
                   (w['routine_id'],0,int(time.time()),json.dumps(old)))
    old_aliases=set()
    for existing in list(defaults.values())+[json.loads(r[0]) for r in db.execute('SELECT json FROM warranty_versions WHERE (routine_id,version) IN (SELECT routine_id,MAX(version) FROM warranty_versions GROUP BY routine_id)').fetchall()]:
        if existing['routine_id'] != w['routine_id']:old_aliases |= {' '.join(x.lower().split()) for x in existing['aliases']}
    if set(w['aliases']) & old_aliases:raise ValueError('An alias belongs to a different routine')
    drift=compare_warranties(old,w) if old else {'verdict':'SAFE','findings':[]}
    if drift['verdict']=='BREAKING' and confirm_breaking is not True:raise ValueError('Breaking safety drift: explicit confirmation required; review changes before saving')
    version=row[0]+1 if row else 1
    major=int(str(old.get('warranty_version','1.0.0')).split('.')[0]) if old else 1
    w['warranty_version']=f'{major}.{version}.0'
    # preview mandatory and nonzero side-effect mutations are permitted but reported, not silently hidden.
    audit=audit_warranty(w,universe)
    db.execute('INSERT INTO warranty_versions(routine_id,version,created_at,json) VALUES(?,?,?,?)',(w['routine_id'],version,int(time.time()),json.dumps(w)))
    return {'warranty':w,'version':version,'drift':drift,'audit':audit}
