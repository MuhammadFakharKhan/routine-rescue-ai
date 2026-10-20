"""Independent, deterministic, stdlib-only routine warranty test engine.

Only local simulated state is handled; no actual IoT/Alexa integrations.
"""
import copy
from collections import defaultdict

SUPPORTED_FAULTS = {"ack_without_effect", "readback_unavailable", "permission_revoked", "timeout_after_commit", "partial_rollback"}


def _validate(scenario):
    if scenario.get("schema_version") != "1.0.0":
        raise ValueError("Scenario schema_version must be 1.0.0")
    warranty = scenario.get("warranty")
    if not isinstance(warranty, dict) or warranty.get("schema_version") != "1.0.0":
        raise ValueError("A v1.0.0 warranty object is required")
    for key in ("steps", "postconditions", "forbidden_operations", "recovery"):
        if key not in warranty:
            raise ValueError("Warranty missing " + key)
    ids = [s["step_id"] for s in warranty["steps"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate step IDs")
    for f in scenario.get("faults", []):
        if f["kind"] not in SUPPORTED_FAULTS:
            raise ValueError("Unrecognized fault " + f["kind"])
        if f["at_step_id"] not in ids:
            raise ValueError("Fault references missing step " + f["at_step_id"])
        if f["occurrences"] < 1:
            raise ValueError("Fault occurrences must be positive")
    return warranty


def run_scenario(scenario):
    """Run an isolated scenario; return a reproducible, serializable report.

    ACK is never sufficient evidence of success; separate readback determines
    VERIFIED / DEGRADED / UNVERIFIED. Supports at most one policy-approved retry.
    """
    warranty = _validate(scenario)
    state = copy.deepcopy(scenario.get("initial_state", {}))
    approvals = set(scenario.get("approvals", []))
    remaining_faults = defaultdict(int)
    for f in scenario.get("faults", []):
        remaining_faults[(f["at_step_id"], f["kind"])] += f["occurrences"]
    initial = copy.deepcopy(state)
    events = []
    unknown_fields = set()
    retries = 0
    forbidden = set(warranty["forbidden_operations"])
    recovery = warranty["recovery"]
    auto_retry = set(recovery.get("auto_retry_operations", []))

    def take_fault(step_id):
        for kind in ("permission_revoked", "ack_without_effect", "timeout_after_commit", "readback_unavailable", "partial_rollback"):
            key = (step_id, kind)
            if remaining_faults[key] > 0:
                remaining_faults[key] -= 1
                return kind
        return None

    def perform(step, retry=False):
        step_id = step["step_id"]
        operation = step["operation"]
        target, field, value = step["target"], step["field"], step["value"]
        entry = {"step_id": step_id, "operation": operation, "retry": retry, "target": target}
        if operation in forbidden:
            entry.update(ack="BLOCKED", readback="UNVERIFIED", reason="forbidden_operation")
            events.append(entry)
            return "BLOCKED"
        if step.get("requires_approval") and operation not in approvals:
            entry.update(ack="BLOCKED", readback="UNVERIFIED", reason="approval_required")
            events.append(entry)
            return "BLOCKED"
        fault = take_fault(step_id)
        if fault == "permission_revoked":
            entry.update(ack="BLOCKED", readback="UNVERIFIED", reason="permission_revoked")
            events.append(entry)
            return "BLOCKED"
        target_existed = target in state
        field_existed = field in state.get(target, {})
        previous_value = copy.deepcopy(state.get(target, {}).get(field))
        if fault not in ("ack_without_effect",):
            state.setdefault(target, {})[field] = value
        if fault == "partial_rollback":
            if field_existed:
                state[target][field] = previous_value
            else:
                del state[target][field]
                if not target_existed and not state[target]:
                    del state[target]
        entry["ack"] = "TIMEOUT" if fault == "timeout_after_commit" else "SUCCESS"
        if fault == "readback_unavailable":
            unknown_fields.add((target, field))
            entry["readback"] = "UNKNOWN"
        else:
            unknown_fields.discard((target, field))
            observed = state.get(target, {}).get(field)
            entry["readback"] = "VERIFIED" if observed == value else "MISMATCH"
        entry["fault"] = fault
        events.append(entry)
        return entry["readback"]

    for step in warranty["steps"]:
        outcome = perform(step)
        if (outcome == "MISMATCH" and step["operation"] in auto_retry and
                not step.get("requires_approval") and retries < min(1, int(recovery.get("max_auto_retries", 0)))):
            retries += 1
            perform(step, retry=True)

    violations = []
    unknown = False
    for p in warranty["postconditions"]:
        target, field, expected = p["target"], p["field"], p["equals"]
        if (target, field) in unknown_fields:
            unknown = True
            violations.append({"target": target, "field": field, "expected": expected, "actual": "UNKNOWN"})
        else:
            observed = state.get(target, {}).get(field)
            if observed != expected:
                violations.append({"target": target, "field": field, "expected": expected, "actual": observed})
    blocked = any(e["ack"] == "BLOCKED" for e in events)
    if any(v["actual"] != "UNKNOWN" for v in violations) or blocked:
        outcome = "DEGRADED"
    elif unknown:
        outcome = "UNVERIFIED"
    elif retries:
        outcome = "RECOVERED"
    else:
        outcome = "VERIFIED"

    expectation = scenario.get("expected")
    check = None
    if expectation is not None:
        check = (outcome == expectation["workflow_outcome"] and violations == expectation["violations"])
    return {"scenario_id": scenario.get("scenario_id", "unnamed"),
            "outcome": outcome, "expected_matched": check, "retries": retries,
            "initial_state": initial, "final_state": state,
            "violations": violations, "events": events}
