# Coding Agent Instructions — RoutineRescue AI

1. Keep this an independent **Alexa+-style simulation**, never imply real Amazon access.
2. Keep localhost-only, stdlib-only runtime unless a dependency is truly necessary.
3. Prioritize truthful outcomes over cosmetic success messages. `UNKNOWN` is not `VERIFIED`.
4. Never auto-run `UNLOCK`; require explicit approval for `LOCK`.
5. Preserve IntentProof schema v1.0.0 compatibility; update both repositories together if you change it.
6. Tests are required for any change to retry, permission or state semantics.
7. No secrets, personal data, actual smart-lock access or copyrighted Amazon branding in the demo.
8. Clearly mark features as implemented vs planned. Read `docs/rule.md` before preparing Devpost submission.
