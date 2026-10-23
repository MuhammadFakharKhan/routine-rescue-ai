"""Local-only, dependency-free RoutineRescue web service and static UI.

Run: python -m app.server --port 8765
This controls simulated objects in SQLite, never real Amazon or smart-home devices.
"""
import argparse
import copy
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .engine import run_scenario
from .assurance import audit_warranty, compare_warranties, verify_recovery
from .warranties import CATALOG, draft, save_version
from .incident import make_incident

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
WARRANTIES = {w['routine_id']: w for w in (
    json.loads(path.read_text(encoding='utf-8'))
    for path in sorted((ROOT/'examples').glob('*-warranty.json')))}
WARRANTY = WARRANTIES['good-night']
INITIAL_STATE = {"living_light": {"power": "on"}, "front_door": {"locked": False, "open": False}, "alarm": {"time": None}, "desk_light": {"power": "off"}, "ambient_light": {"power": "on"}}
DB_PATH = Path(os.environ.get("ROUTINE_RESCUE_DB", str(ROOT / "data" / "routine_rescue.sqlite")))
VALID_FAULTS = {"none": None, "false_success": "ack_without_effect", "false_success_once": "ack_without_effect",
                "unavailable_readback": "readback_unavailable", "permission_revoked": "permission_revoked",
                "timeout_after_commit": "timeout_after_commit", "partial_rollback": "partial_rollback",
                "unexpected_side_effect":"unexpected_side_effect"}


@contextmanager
def connect():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, json TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, scenario TEXT NOT NULL, report TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS recovery_proofs (id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, created_at INTEGER NOT NULL, proof TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS warranty_versions (routine_id TEXT NOT NULL, version INTEGER NOT NULL, created_at INTEGER NOT NULL, json TEXT NOT NULL, PRIMARY KEY(routine_id,version))")
        if con.execute("SELECT 1 FROM kv WHERE key='state'").fetchone() is None:
            con.execute("INSERT INTO kv (key,json) VALUES (?,?)", ("state", json.dumps(INITIAL_STATE)))
            con.commit()
        yield con
    finally:
        con.close()

def get_state(con):
    row = con.execute("SELECT json FROM kv WHERE key='state'").fetchone()
    return json.loads(row[0])


def all_warranties():
    result = copy.deepcopy(WARRANTIES)
    with connect() as con:
        latest=con.execute('SELECT w.json FROM warranty_versions w JOIN (SELECT routine_id, MAX(version) AS version FROM warranty_versions GROUP BY routine_id) v ON v.routine_id=w.routine_id AND v.version=w.version').fetchall()
    for row in latest: result[json.loads(row[0])['routine_id']]=json.loads(row[0])
    return result


def resolve(text):
    cleaned = " ".join(text.strip().lower().replace("!", "").replace(".", "").split())
    return next((w for w in all_warranties().values() if cleaned in w["aliases"]), None)


def preview(text):
    w = resolve(text)
    if w is None:
        return {"matched": False, "message": "No saved routine matches that phrase. Try Good Night, Focus Mode or Leaving Home."}
    return {"matched": True, "routine": w["name"], "matched_phrase": text, "steps": w["steps"],
            "postconditions": w["postconditions"], "forbidden_operations": w["forbidden_operations"],
            "requires_approval": [s["operation"] for s in w["steps"] if s["requires_approval"]],
            "audit":audit_warranty(w,INITIAL_STATE), "warranty_version":w.get("warranty_version","1.0.0")}


def build_scenario(state, fault_mode="none", approve_sensitive=False, warranty=None):
    if fault_mode not in VALID_FAULTS:
        raise ValueError("Invalid fault mode. Choose one of: " + ", ".join(VALID_FAULTS))
    faults = []
    if fault_mode != "none":
        steps=(warranty or WARRANTY)['steps']
        at_step = next((step['step_id'] for step in steps if step['requires_approval']), steps[0]['step_id']) if fault_mode == 'permission_revoked' else steps[0]['step_id']
        faults = [{"at_step_id": at_step, "kind": VALID_FAULTS[fault_mode],
                   "occurrences": 2 if fault_mode in ("false_success", "partial_rollback") else 1}]
    return {"schema_version": "1.0.0", "scenario_id": "routine-rescue-" + uuid.uuid4().hex[:12],
            "description": "Synthetic RoutineRescue run; NOT a real Alexa+ or device failure",
            "warranty": copy.deepcopy(warranty or WARRANTY), "initial_state": copy.deepcopy(state),
            "approvals": ["LOCK"] if approve_sensitive else [], "seed": 0, "faults": faults}


def execute(utterance, fault_mode, approve_sensitive):
    warranty = resolve(utterance)
    if warranty is None:
        raise ValueError("Unknown routine. Try Good Night, Focus Mode or Leaving Home.")
    with connect() as con:
        scenario = build_scenario(get_state(con), fault_mode, approve_sensitive, warranty)
        report = run_scenario(scenario)
        scenario["expected"] = {"workflow_outcome": report["outcome"], "violations": report["violations"]}
        con.execute("UPDATE kv SET json=? WHERE key='state'", (json.dumps(report["final_state"]),))
        con.execute("INSERT INTO runs (id,created_at,scenario,report) VALUES(?,?,?,?)",
                    (scenario["scenario_id"], int(time.time()), json.dumps(scenario), json.dumps(report)))
        con.commit()
    return {"receipt": report, "export_path": "/api/exports/latest",
            "audit": audit_warranty(warranty,INITIAL_STATE)}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            with connect() as con:
                return self.respond(200, {"state": get_state(con), "simulation": True})
        if path == "/api/warranty":
            return self.respond(200, all_warranties().get('good-night',WARRANTY))
        if path == "/api/catalog":
            return self.respond(200, {'actions':CATALOG,'fields':sorted([a+'.'+b for a,b in {
                ('living_light','power'),('desk_light','power'),('ambient_light','power'),('front_door','locked'),('alarm','time')}])})
        if path.startswith('/api/warranties/versions/'):
            rid=path.rsplit('/',1)[-1]
            with connect() as con:
                rows=con.execute('SELECT version,created_at,json FROM warranty_versions WHERE routine_id=? ORDER BY version DESC',(rid,)).fetchall()
            return self.respond(200,[{'version':x,'created_at':t,'warranty':json.loads(raw)} for x,t,raw in rows])
        if path.startswith('/api/warranties/item/'):
            w=all_warranties().get(path.rsplit('/',1)[-1]);return self.respond(200,w) if w else self.respond(404,{'error':'Unknown warranty'})
        if path == "/api/warranties":
            return self.respond(200, [{"routine_id":w['routine_id'], "name":w['name'], "aliases":w['aliases'],
                                       "audit":audit_warranty(w,INITIAL_STATE)} for w in all_warranties().values()])
        if path.startswith('/api/audit/'):
            w=all_warranties().get(path.split('/')[-1])
            return self.respond(200,audit_warranty(w,INITIAL_STATE)) if w else self.respond(404,{"error":"Unknown warranty"})
        if path == "/api/history":
            with connect() as con:
                rows = con.execute("SELECT id, created_at, report FROM runs ORDER BY created_at DESC LIMIT 20").fetchall()
            return self.respond(200, [{"id": x, "created_at": t, "report": json.loads(r)} for x, t, r in rows])
        if path == "/api/incidents/latest":
            with connect() as con:
                row=con.execute('SELECT scenario,report FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
            if row is None:return self.respond(404, {'error':'Run a routine before exporting an incident'})
            scenario,report=map(json.loads,row)
            with connect() as con:
                r=con.execute('SELECT proof FROM recovery_proofs WHERE scenario_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(scenario['scenario_id'],)).fetchone()
            return self.respond(200,make_incident(scenario,report,json.loads(r[0]) if r else None))
        if path == "/api/exports/latest":
            with connect() as con:
                row = con.execute("SELECT scenario FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
            if row is None:
                return self.respond(404, {"error": "Run a routine before exporting a scenario"})
            return self.respond(200, json.loads(row[0]))
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8"),
                  "/virtual-home-2d.css": ("virtual-home-2d.css", "text/css; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/virtual-home-2d.js": ("virtual-home-2d.js", "text/javascript; charset=utf-8"),
                  "/virtual-home-state.js": ("virtual-home-state.js", "text/javascript; charset=utf-8")}
        if path not in static:
            return self.respond(404, {"error": "Not found"})
        filename, mimetype = static[path]
        data = (WEB / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/preview", "/api/execute", "/api/reset", "/api/recover", "/api/warranties/save", "/api/warranties/draft"):
            return self.respond(404, {"error": "Not found"})
        try:
            # A localhost-only app can still be targeted by remote websites.
            # Require JSON and reject browser cross-origin mutation attempts.
            origin=self.headers.get('Origin')
            host=self.headers.get('Host','')
            if origin and origin not in (f'http://{host}',f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                return self.respond(403,{'error':'Cross-origin mutation refused'})
            if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                return self.respond(415,{'error':'Expected application/json'})
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 16384:
                return self.respond(413, {"error": "Request too large"})
            obj = json.loads(self.rfile.read(size)) if size else {}
            if not isinstance(obj, dict):
                raise ValueError("Expected JSON object")
            if path == '/api/warranties/draft':
                with connect() as con: state=get_state(con)
                w=draft(obj,state)
                old=all_warranties().get(w['routine_id'])
                return self.respond(200,{'warranty':w,'audit':audit_warranty(w,INITIAL_STATE),
                    'drift':compare_warranties(old,w) if old else {'verdict':'SAFE','findings':[]}})
            if path == '/api/warranties/save':
                w=obj.get('warranty')
                with connect() as con:
                    result=save_version(con,w,WARRANTIES,obj.get('confirm_safety_drift',False),INITIAL_STATE)
                    con.commit()
                return self.respond(200,result)
            if path == "/api/preview":
                return self.respond(200, preview(str(obj.get("utterance", ""))))
            if path == '/api/recover':
                if obj.get('approve_recovery') is not True:
                    raise ValueError('Recovery must be explicitly approved')
                with connect() as con:
                    row=con.execute('SELECT scenario,report FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
                    if not row: raise ValueError('Run a routine first')
                    scenario,original=map(json.loads,row)
                    before=get_state(con)
                    failed={(v['target'],v['field']) for v in original['violations'] if v.get('actual')!='UNKNOWN'}
                    steps=[step for step in scenario['warranty']['steps']
                           if (step['target'],step['field']) in failed and step['risk']=='low'
                           and not step['requires_approval'] and step['operation'] not in scenario['warranty']['forbidden_operations']]
                    after=copy.deepcopy(before)
                    for step in steps:after.setdefault(step['target'],{})[step['field']]=step['value']
                    permitted={(step['target'],step['field']) for step in steps}
                    proof=verify_recovery(before,after,permitted,scenario['warranty']['postconditions']+scenario['warranty'].get('invariants',[]))
                    proof['attempted']=bool(steps)
                    if steps and proof['scope_verified']:
                        con.execute("UPDATE kv SET json=? WHERE key='state'",(json.dumps(after),))
                        con.execute('INSERT INTO recovery_proofs VALUES (?,?,?,?)',(uuid.uuid4().hex,scenario['scenario_id'],int(time.time()),json.dumps(proof)))
                        con.commit()
                return self.respond(200,proof)
            if path == "/api/reset":
                with connect() as con:
                    con.execute("UPDATE kv SET json=? WHERE key='state'", (json.dumps(INITIAL_STATE),))
                    con.commit()
                return self.respond(200, {"state": copy.deepcopy(INITIAL_STATE), "reset": True})
            if type(obj.get("approve_sensitive", False)) is not bool:
                raise ValueError("approve_sensitive must be boolean")
            return self.respond(200, execute(str(obj.get("utterance", "")), str(obj.get("fault_mode", "none")), obj.get("approve_sensitive", False)))
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            return self.respond(400, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("RoutineRescue:", fmt % args)


def main():
    parser = argparse.ArgumentParser(description="Launch local-only simulated Alexa+-style routine assistant")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        parser.error("This no-auth prototype intentionally binds only to localhost")
    server = HTTPServer((args.host, args.port), Handler)
    print(f"RoutineRescue demo: http://{args.host}:{args.port}")
    print("Simulated devices only. Not connected to Alexa+ or any physical devices.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
