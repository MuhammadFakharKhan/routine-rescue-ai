"""Semantic warranty assurance: mutation adequacy, drift checks and recovery bounds.

Runs entirely offline. Coverage is a bounded estimate over declared steps, NOT
proof that omitted actions or unmodeled physical side effects cannot occur.
"""
import copy


def fields_changed(before, after):
    changes = []
    for target in sorted(set(before) | set(after)):
        a, b = before.get(target, {}), after.get(target, {})
        for field in sorted(set(a) | set(b)):
            if a.get(field) != b.get(field):
                changes.append({"target": target, "field": field,
                                "before": a.get(field), "after": b.get(field)})
    return changes


def verify_recovery(before, after, allowed, expected=None):
    allowed = set(map(tuple, allowed))
    changes = fields_changed(before, after)
    unexpected = [d for d in changes if (d["target"], d["field"]) not in allowed]
    unmet = []
    for p in expected or []:
        actual = after.get(p["target"], {}).get(p["field"])
        if actual != p["equals"]:
            unmet.append({"target": p["target"], "field": p["field"],
                          "expected": p["equals"], "actual": actual})
    return {"verified": not unexpected and not unmet, "scope_verified": not unexpected,
            "postconditions_verified": not unmet, "changes": changes,
            "unexpected_changes": unexpected, "unmet_postconditions": unmet}


def _other_value(value):
    if isinstance(value, bool): return not value
    if value is None: return '__unexpected__'
    if isinstance(value, (int, float)): return value + 1
    return '__unexpected__' if value != '__unexpected__' else '__different__'


def audit_warranty(warranty, universe=None):
    """Bounded mutation assessment of action outcomes and declared side-effect candidates.

    A survived mutation means the modeled contract would not reject it. A killed
    mutation does NOT prove real-world safety, sensor honesty, or completeness.
    """
    if not isinstance(warranty,dict): raise ValueError('warranty must be an object')
    steps=warranty.get('steps',[])
    if not isinstance(steps,list) or not steps: raise ValueError('warranty.steps must be a nonempty list')
    assertions=warranty.get('postconditions',[])+warranty.get('invariants',[])
    candidates={}; modeled_steps=set()
    for step in steps:
        key=(step['target'],step['field']); modeled_steps.add(key)
        candidates[key]={'desired':step['value'],'kind':'step_outcome'}
    for item in warranty.get('side_effect_candidates',[]):
        key=(item['target'],item['field'])
        if key not in candidates: candidates[key]={'desired':item.get('baseline'),'kind':'side_effect'}
    if universe is not None:
        if not isinstance(universe,dict):raise ValueError('universe must be a state dictionary')
        for target,fields in universe.items():
            if not isinstance(fields,dict):raise ValueError('universe state fields must be objects')
            for field,baseline in fields.items():
                key=(target,field)
                if key not in candidates:
                    candidates[key]={'desired':baseline,'kind':'environment_side_effect'}
    for item in warranty.get('invariants',[]):
        key=(item['target'],item['field'])
        if key not in candidates: candidates[key]={'desired':item['equals'],'kind':'invariant'}
    guarded={(p['target'],p['field']) for p in warranty.get('unchanged_fields',[])}
    results=[]; baseline_issues=[]
    for (target,field), data in sorted(candidates.items()):
        desired=data['desired']; mutated=_other_value(desired)
        matching=[p for p in assertions if (p['target'],p['field'])==(target,field)]
        if data['kind']=='step_outcome' and matching and any(p['equals']!=desired for p in matching):
            baseline_issues.append(f'{target}.{field}: declared assertion conflicts with action result')
        protection=any(p['equals']!=mutated for p in matching)
        if (target,field) in guarded and data['kind'] in ('side_effect','environment_side_effect'): protection=True
        if data['kind']=='step_outcome' and any(p['equals']!=desired for p in matching):protection=False
        results.append({'target':target,'field':field,'kind':data['kind'],'desired':desired,
            'mutated':mutated,'status':'KILLED' if protection else 'SURVIVED',
            'reason':'Enforced by assertion or unchanged-field rule' if protection else 'No assertion or unchanged-field rule catches this modeled change'})
    killed=sum(r['status']=='KILLED' for r in results)
    return {'warranty_id':warranty.get('warranty_id','unknown'),'mutants':len(results),
            'killed':killed,'survived':len(results)-killed,
            'coverage_percent':round(100*killed/len(results),1) if results else 0,
            'findings':results,'baseline_consistent':not baseline_issues,'baseline_issues':baseline_issues,
            'limitation':'Bounded coverage over declared actions, candidates and optionally supplied environment inventory; not a physical safety guarantee.'}


def compare_warranties(old,new):
    findings=[]
    def add(severity,path,message):
        findings.append({"severity":severity,"path":path,"message":message})
    olds={s['step_id']:s for s in old.get('steps',[])}
    news={s['step_id']:s for s in new.get('steps',[])}
    for sid,step in olds.items():
        latest=news.get(sid)
        if latest is None:
            add('WARNING',f'steps.{sid}','Previously declared step removed')
            continue
        if step.get('requires_approval') and not latest.get('requires_approval'):
            add('CRITICAL',f'steps.{sid}.requires_approval','Approval requirement removed')
        if step.get('risk')=='sensitive' and latest.get('risk')!='sensitive':
            add('CRITICAL',f'steps.{sid}.risk','Sensitive operation downgraded')
        for prop in ('operation','target','field','value'):
            if step.get(prop)!=latest.get(prop):
                add('WARNING',f'steps.{sid}.{prop}',f'Execution changed: {prop}')
    for sid in news.keys()-olds.keys():
        add('WARNING',f'steps.{sid}','New action added to approved routine')
    for operation in sorted(set(old.get('forbidden_operations',[]))-set(new.get('forbidden_operations',[]))):
        add('CRITICAL','forbidden_operations',f'Previously forbidden operation is allowed: {operation}')
    def key(p): return (p['target'],p['field'],jsonlike(p.get('equals')))
    for label in ('postconditions','invariants'):
        gone={key(p) for p in old.get(label,[])} - {key(p) for p in new.get(label,[])}
        for target,field,_ in sorted(gone):
            add('CRITICAL',label,f'Protection removed or weakened: {target}.{field}')
    old_r=old.get('recovery',{});new_r=new.get('recovery',{})
    if new_r.get('max_auto_retries',0)>old_r.get('max_auto_retries',0):
        add('WARNING','recovery.max_auto_retries','Automatic retry budget increased')
    if old.get('verification',{}).get('require_readback') and not new.get('verification',{}).get('require_readback'):
        add('CRITICAL','verification.require_readback','Independent observation disabled')
    if not old.get('verification',{}).get('unknown_is_success',False) and new.get('verification',{}).get('unknown_is_success',False):
        add('CRITICAL','verification.unknown_is_success','Unknown observations promoted to success')
    def guard_keys(doc, label):
        return {(i['target'],i['field']) for i in doc.get(label,[])}
    for target,field in sorted(guard_keys(old,'unchanged_fields')-guard_keys(new,'unchanged_fields')):
        add('CRITICAL','unchanged_fields',f'Unchanged-field protection removed: {target}.{field}')
    for target,field in sorted(guard_keys(old,'side_effect_candidates')-guard_keys(new,'side_effect_candidates')):
        add('WARNING','side_effect_candidates',f'Modeled side-effect candidate removed: {target}.{field}')
    old_aliases=set(old.get('aliases',[]));new_aliases=set(new.get('aliases',[]))
    for alias in sorted(new_aliases-old_aliases):
        add('INFO','aliases',f'Alias added: {alias}')
    highest={f['severity'] for f in findings}
    return {"verdict":"BREAKING" if 'CRITICAL' in highest else 'REVIEW' if 'WARNING' in highest else 'SAFE',
            "findings":findings}


def jsonlike(value):
    import json
    return json.dumps(value,sort_keys=True)
