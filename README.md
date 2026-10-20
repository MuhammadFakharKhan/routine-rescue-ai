# RoutineRescue AI — simulated Alexa+-style assistant

**Status:** runnable local prototype, not production software. **No connection to Amazon Alexa+, real devices, voice services or paid AI models.** Independent simulation only.

## The problem

A multi-action assistant may acknowledge an action even when its intended result did not occur, or when the actual state is unknown. People need a truthful summary and an opportunity to approve sensitive actions.

## What this starter does (implemented)

- Recognizes two approved aliases for the synthetic Good Night routine (`good night`, `time for bed`), rejects unknown commands.
- Previews a versioned routine warranty: lights off; simulated front door locked; alarm at 07:00; never unlock.
- Requires explicit approval for the sensitive `LOCK` operation.
- Runs against SQLite-backed **virtual** device state.
- Supports fault injection: false success, recovery after one failed acknowledgement, unavailable state readback, revoked permission, timeout after commit, and simulated post-write reversion. The reversion fault is not a real compensating transaction.
- Checks **observed state**, not only action acknowledgement; labels outcomes `VERIFIED`, `RECOVERED`, `DEGRADED` or `UNVERIFIED`.
- Generates a self-contained **IntentProof scenario JSON** that reproduces the synthetic run in the separate open-source toolkit.
- Offers a browser dashboard and records the 20 latest run receipts.

### Run on your laptop (Python 3.10+, no pip required)

```bash
cd routine-rescue-ai
python -m app.server --port 8765
```

Visit **http://127.0.0.1:8765**. This app binds only to localhost and uses no cloud service. Stop with Ctrl+C.

### Demo sequence

1. Click **Reset devices**. Enter `good night`, then **Preview** to inspect the warranty.
2. Tick approval for the virtual lock; select **False success twice**, execute. Observe `DEGRADED`, a light still on and an accurate receipt.
3. Click **Export IntentProof test JSON** to download `exported-scenario.json`.
4. In the **other repository**, run `intentproof run exported-scenario.json` to reproduce this result.
5. Reset devices and select **False success once** to show a policy-approved retry and `RECOVERED`.
6. Select **State unavailable** to see `UNVERIFIED`, not false success.

### Run tests

```bash
python -m unittest discover -s tests -v
```

### API

- `GET /api/status` — current virtual device state.
- `GET /api/warranty` — saved routine warranty.
- `POST /api/preview` with `{ "utterance": "good night" }`.
- `POST /api/execute` with `{ "utterance": "good night", "approve_sensitive": true, "fault_mode": "false_success" }`.
- `POST /api/reset` with `{}` — reset the virtual state.
- `GET /api/history` — recent executions.
- `GET /api/exports/latest` — ready-to-run IntentProof JSON.

### Structure

`app/server.py` is a local stdlib HTTP service + SQLite persistence. `app/engine.py` is a self-contained deterministic virtual executor. `web/` is the browser UI. `examples/` holds v1 JSON warranty and scenario. `contracts/` holds matching v1 JSON schemas. `docs/` holds separate engineering/implementation/submission specifications.

### Limits and safeguards

- Bounded, **deterministic agentic simulation**; no real language model call or Echo control.
- Only one hard-coded synthetic routine and a few matching aliases; no real free-form speech understanding.
- Recovery is restricted to one retry of `LIGHT_OFF` on a known mismatch; no automatic unlock, external API mutation, or uncontrolled rollback.
- SQLite data is local. The built-in web server has no authentication: **do not expose it to the network**.
- Independent `readback` in the virtual device model is not proof of actual hardware reliability.
- Faults are simulated for demonstration; never present them as real Alexa+ incidents.

## Hackathon route

Primary track: **Alexa+ simulated experience**, explicitly provided as an alternate route in the 2026 official rules. The additional **Open Source mini-challenge** is the separate IntentProof repository. Submit one Devpost entry with both URLs. See `docs/rule.md` for full checklists and https://amazonappdev2026.devpost.com/rules .

See `docs/integration.md` for how to move a failed incident to IntentProof.
