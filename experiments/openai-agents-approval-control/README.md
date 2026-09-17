# OpenAI Agents SDK serialized-approval control

This negative-control harness tests ordinary per-call function-tool approval
across native `RunState` serialization and restoration.

Run either recorded release:

```bash
bash experiments/openai-agents-approval-control/run.sh 0.22.0
bash experiments/openai-agents-approval-control/run.sh 0.22.2
```

For each run, three unchanged approved-A snapshots must restore and execute A;
three same-call-ID raw invocation mutations to B must raise `ModelBehaviorError`
and execute nothing; and direct unapproved B must pause. The deterministic model
and in-memory ledger are local fixtures.

This is not a vulnerability test for sticky approval policies or arbitrary
forgery of every canonical serialized field.

