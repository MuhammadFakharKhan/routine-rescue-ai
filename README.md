# RoutineRescue AI — Behavioral Warranties for Action-Taking Assistants

**An independently simulated Alexa+-style experience** that turns multi-step routines into user-approved promises, detects incomplete outcomes and unexpected side effects, supports explicitly approved low-risk recovery, and exports reproducible evidence for IntentProof.

> **Important:** This is an independent, **local virtual-device simulator**. It does not connect to Alexa+, Amazon services, a microphone, or any physical device. Its modeled observations and audit scores are **not** production safety guarantees.

## Start in under a minute

Requires **Python 3.11+**. There are **no runtime dependencies or paid APIs**.

```powershell
cd routine-rescue-ai
python -m app.server
```

Open **http://127.0.0.1:8765**. The server binds only to localhost and stores synthetic device state, warranties, and incident receipts in `data/routine_rescue.sqlite`.

### The end-user workflow

1. Preview **Good Night**, **Focus Mode**, or **Leaving Home**, or create your own routine in **Behavioral Warranty Studio**.
2. Choose each simulated action and optional other device fields that must **remain unchanged**. Preview the bounded mutation score and any safety drift.
3. Save a versioned warranty. Earlier versions remain in local SQLite. Safety-breaking changes require explicit confirmation; unsafe actions like `UNLOCK` cannot be authored using the builder.
4. Execute a routine with human approval for simulated sensitive locking. Optionally inject a false success, unavailable readback, timeout, or unexpected side effect.
5. Read the execution receipt. A successful action acknowledgement is not sufficient for verification.
6. If a low-risk action failed, explicitly approve a minimal repair. The recovery check compares changes against the permitted field scope.
7. Export **Incident v2 JSON**, containing warranty provenance, evidence, recovery proof (if one was recorded), and a checksummed **v1 replay fixture** for IntentProof.

### Supported simulated actions

`LIGHT_ON`, `LIGHT_OFF`, `LOCK`, and `SET_ALARM`, with a strict allowlist of virtual devices/fields. Locking needs explicit approval; unlocking is forbidden. No arbitrary code, network tools, or physical actuators are exposed.

### What Promise Mutation Coverage really means

The engine mutates declared **step outcomes** plus explicitly modeled **side-effect candidates**. Protection is represented through postconditions, invariants, or `unchanged_fields`. A surviving mutation indicates a gap in the modeled warranty. **Even 100% does not prove safety or guarantee detection of unknown effects.**

### Developer interfaces

| Endpoint | Method | Use |
|---|---|---|
| `/api/status` | GET | Simulated observed state |
| `/api/catalog` | GET | Allowlisted builder actions and fields |
| `/api/warranties` | GET | Current saved routines |
| `/api/warranties/item/{id}` | GET | Full current warranty |
| `/api/warranties/versions/{id}` | GET | Immutable revision history |
| `/api/warranties/draft` | POST | Validate builder form, preview drift and audit |
| `/api/warranties/save` | POST | Save validated revision with explicit drift acknowledgement |
| `/api/preview` | POST | Preview approved execution promise |
| `/api/execute` | POST | Execute simulated routine and create receipt |
| `/api/recover` | POST | User-approved low-risk repair with change-scope proof |
| `/api/incidents/latest` | GET | Versioned incident v2 export |
| `/api/exports/latest` | GET | Legacy v1 replay scenario export |
| `/api/history` | GET | Recent synthetic runs |
| `/api/reset` | POST | Reset local virtual state |

POST routes accept JSON only. Browser cross-origin requests are rejected and the server binds only to loopback. These are *basic demo protections*, not a replacement for real authentication, authorization or CSRF defenses in an internet-exposed service.

### Testing

```powershell
python -m unittest discover -s tests -v
```

Use an isolated DB when experimenting:

```powershell
$env:ROUTINE_RESCUE_DB="$env:TEMP\routine-rescue-demo.sqlite"
python -m app.server
```

### Cross-repository integration

After running a virtual routine, click **Export incident v2** and run this from the separate IntentProof checkout:

```powershell
$env:PYTHONPATH="src"
python -m intentproof incident C:\path\to\exported-incident-v2.json --format markdown -o incident-report.md
```

See [docs/ENGINEERING_V3.md](docs/ENGINEERING_V3.md) for JSON versioning, trust boundaries, editor restrictions, and test coverage. Preserve the two repositories separately for the Open Source mini-challenge.

### Known limitations

- No live Alexa+/MCP connection and no physical device-state observation.
- The virtual home is a local visualization of SQLite-backed simulated observations. Its optional `front_door.open` field is separate from `front_door.locked`; an unlocked door is never presented as physically open.
- The default virtual-home view is an inline SVG/CSS animated 2D room, so it does not require WebGL, a GPU renderer, or network-loaded assets.
- Text and preset controls are simulated, not production speech recognition or general autonomous planning.
- Routine editor supports only a fixed set of safe virtual actions; existing custom YAML/Python logic is intentionally not executed.
- The mutation score includes **only explicitly modeled** expected fields and candidate side effects.
- Recovery proofs show state differences in the local simulator; they cannot prove actual physical-world effects.
- Version 2 incident SHA-256 is a **checksum**, not tamper-proof authentication or a digital signature.
- Persistent SQLite data stays on your computer; export files may include routine context, so review them before sharing.

**License:** MIT. See `LICENSE`.
