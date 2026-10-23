"""Versioned, self-contained, synthetic incident export.

Replay fixtures remain v1; incident envelopes are v2. The digest protects
against accidental edits only (not authenticity or malicious modification).
"""
import copy
import hashlib
import json
from datetime import datetime, timezone

VERSION='2.0.0'

def checksum(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()

def make_incident(scenario, report, recovery_proof=None):
    warranty=scenario['warranty']
    return {'schema_version':VERSION,
            'incident_id':'incident-'+scenario['scenario_id'],
            'created_at':datetime.now(timezone.utc).isoformat(),
            'source':{'application':'RoutineRescue AI','simulation':True,
                      'routine_id':warranty['routine_id'],'warranty_version':warranty.get('warranty_version','1.0.0')},
            'intent':{'approved_goal':warranty['name'],'trigger_phrases':warranty['aliases']},
            'contract':{'postconditions':copy.deepcopy(warranty['postconditions']),
                        'invariants':copy.deepcopy(warranty.get('invariants',[])),
                        'unchanged_fields':copy.deepcopy(warranty.get('unchanged_fields',[]))},
            'execution':{'initial_state':copy.deepcopy(report['initial_state']),
                         'final_state':copy.deepcopy(report['final_state']),
                         'events':copy.deepcopy(report['events']),
                         'outcome':report['outcome']},
            'failure':{'violations':copy.deepcopy(report['violations']),
                       'side_effects':copy.deepcopy(report.get('side_effects',[]))},
            'recovery':{'attempted':bool(recovery_proof),'verified':recovery_proof.get('verified') if recovery_proof else None,
                        'proof':copy.deepcopy(recovery_proof) if recovery_proof else None},
            'replay_scenario':copy.deepcopy(scenario),
            'replay_sha256':checksum(scenario),
            'limitations':'Local simulated state only. Digest is an integrity checksum, not a digital signature.'}
