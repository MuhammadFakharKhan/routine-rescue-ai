# Coding-agent rules for this repository

1. Preserve the public v1 test scenario format and the v2 synthetic incident exchange format unless explicitly versioning them.
2. Never claim live Amazon Alexa+, device integration, physical safety, or authenticated MCP access. This is a local simulation and a separate developer toolkit.
3. Run all unit tests before proposing a release. Re-run the combined-package HTTP/CLI integration test when changing the exchange contract.
4. Never execute remote tool code, fetch untrusted endpoints, or expose credentials through the simulator.
5. Maintain mandatory approval for simulated LOCK; never enable UNLOCK in the local builder.
6. Return `UNVERIFIED` when observation is unavailable; action acknowledgements alone are not proofs of success.
7. Mutation coverage is bounded by modeled fields; include inventory fields where available and explain blind spots.
8. Do not silently weaken contract postconditions, invariants, unchanged-field guards, forbidden operations or approval requirements.
9. Separate RoutineRescue AI and IntentProof source repositories: integration is via documented JSON evidence contracts, not shared mutable internals.
