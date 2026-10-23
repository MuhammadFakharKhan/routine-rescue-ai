# RoutineRescue AI — Behavioral Warranty Upgrade

This local-only Alexa+-style simulation includes Good Night, Focus Mode and Leaving Home; an audit of warranty coverage over declared step outcomes; explicit sensitive-action approval; safe recovery limited to low-risk failed fields; and the existing IntentProof JSON scenario export.

```powershell
python -m app.server
python -m unittest discover -s tests -v
```

Open http://127.0.0.1:8765. The home and door are simulated, **not connected to Amazon**. No real locks are controlled. Use `IntentProof` independently to run, audit and diff JSON files. The recovery proof checks local modeled state, not physical outcomes.
