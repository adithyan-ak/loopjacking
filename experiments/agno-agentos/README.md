# Agno AgentOS approval-binding experiment

This harness tests whether the released regular-Agent continuation path binds an
admin approval to the exact tool arguments later executed.

It uses loopback HTTP, synthetic JWT principals, a deterministic local model,
SQLite, and a mock transfer ledger. No model provider, payment system, or external
service is used.

Run a single released version from the repository root:

```bash
bash experiments/agno-agentos/run_version.sh 3.0.9
```

Run the 2.5.5/2.5.6 boundary pair:

```bash
bash experiments/agno-agentos/run_boundary.sh
```

The strict oracle requires all of the following: the maker cannot resolve A's
approval or execute B directly; the distinct approver resolves exact A; the maker
then supplies B through continuation; the registered harmless tool records B; no
approval record displays B; and unchanged A still succeeds. The broader matrix
also records wrong-user, outsider, wrong-session, denial, replay, and exact-action
control behavior.

The output is written under `evidence/agno-agentos/agno-<version>/<timestamp>/`.

