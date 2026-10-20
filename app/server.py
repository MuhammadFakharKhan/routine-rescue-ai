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

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
WARRANTY = json.loads((ROOT / "examples" / "good-night-warranty.json").read_text())
INITIAL_STATE = {"living_light": {"power": "on"}, "front_door": {"locked": False}, "alarm": {"time": None}}
DB_PATH = Path(os.environ.get("ROUTINE_RESCUE_DB", str(ROOT / "data" / "routine_rescue.sqlite")))
VALID_FAULTS = {"none": None, "false_success": "ack_without_effect", "false_success_once": "ack_without_effect",
                "unavailable_readback": "readback_unavailable", "permission_revoked": "permission_revoked",
                "timeout_after_commit": "timeout_after_commit", "partial_rollback": "partial_rollback"}


@contextmanager
def connect():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, json TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, scenario TEXT NOT NULL, report TEXT NOT NULL)")
        if con.execute("SELECT 1 FROM kv WHERE key='state'").fetchone() is None:
            con.execute("INSERT INTO kv (key,json) VALUES (?,?)", ("state", json.dumps(INITIAL_STATE)))
            con.commit()
        yield con
    finally:
        con.close()

def get_state(con):
    row = con.execute("SELECT json FROM kv WHERE key='state'").fetchone()
    return json.loads(row[0])


def resolve(text):
    cleaned = " ".join(text.strip().lower().replace("!", "").replace(".", "").split())
    return WARRANTY if cleaned in WARRANTY["aliases"] else None


def preview(text):
    w = resolve(text)
    if w is None:
        return {"matched": False, "message": "No saved routine matches that phrase. Try 'good night' or 'time for bed'."}
    return {"matched": True, "routine": w["name"], "matched_phrase": text, "steps": w["steps"],
            "postconditions": w["postconditions"], "forbidden_operations": w["forbidden_operations"],
            "requires_approval": [s["operation"] for s in w["steps"] if s["requires_approval"]]}


def build_scenario(state, fault_mode="none", approve_sensitive=False):
    if fault_mode not in VALID_FAULTS:
        raise ValueError("Invalid fault mode. Choose one of: " + ", ".join(VALID_FAULTS))
    faults = []
    if fault_mode != "none":
        at_step = "lock-door" if fault_mode == "permission_revoked" else "lights-off"
        faults = [{"at_step_id": at_step, "kind": VALID_FAULTS[fault_mode],
                   "occurrences": 2 if fault_mode in ("false_success", "partial_rollback") else 1}]
    return {"schema_version": "1.0.0", "scenario_id": "routine-rescue-" + uuid.uuid4().hex[:12],
            "description": "Synthetic RoutineRescue Good Night run; NOT a real Alexa+ or device failure",
            "warranty": copy.deepcopy(WARRANTY), "initial_state": copy.deepcopy(state),
            "approvals": ["LOCK"] if approve_sensitive else [], "seed": 0, "faults": faults}


def execute(utterance, fault_mode, approve_sensitive):
    if resolve(utterance) is None:
        raise ValueError("Unknown routine. Try 'good night' or 'time for bed'.")
    with connect() as con:
        scenario = build_scenario(get_state(con), fault_mode, approve_sensitive)
        report = run_scenario(scenario)
        scenario["expected"] = {"workflow_outcome": report["outcome"], "violations": report["violations"]}
        con.execute("UPDATE kv SET json=? WHERE key='state'", (json.dumps(report["final_state"]),))
        con.execute("INSERT INTO runs (id,created_at,scenario,report) VALUES(?,?,?,?)",
                    (scenario["scenario_id"], int(time.time()), json.dumps(scenario), json.dumps(report)))
        con.commit()
    return {"receipt": report, "export_path": "/api/exports/latest"}


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
            return self.respond(200, WARRANTY)
        if path == "/api/history":
            with connect() as con:
                rows = con.execute("SELECT id, created_at, report FROM runs ORDER BY created_at DESC LIMIT 20").fetchall()
            return self.respond(200, [{"id": x, "created_at": t, "report": json.loads(r)} for x, t, r in rows])
        if path == "/api/exports/latest":
            with connect() as con:
                row = con.execute("SELECT scenario FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
            if row is None:
                return self.respond(404, {"error": "Run a routine before exporting a scenario"})
            return self.respond(200, json.loads(row[0]))
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8")}
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
        if path not in ("/api/preview", "/api/execute", "/api/reset"):
            return self.respond(404, {"error": "Not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 16384:
                return self.respond(413, {"error": "Request too large"})
            obj = json.loads(self.rfile.read(size)) if size else {}
            if not isinstance(obj, dict):
                raise ValueError("Expected JSON object")
            if path == "/api/preview":
                return self.respond(200, preview(str(obj.get("utterance", ""))))
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
