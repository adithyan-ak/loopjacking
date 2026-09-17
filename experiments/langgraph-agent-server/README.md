# LangGraph Agent Server approval-binding experiment

This harness tests a conditional in-memory composition in which a maker may update
a shared pending thread but may not resume it or execute B directly. A distinct
approver may resume and execute but does not perform the update.

The harness uses loopback HTTP, synthetic JWT principals, LangGraph's documented
Auth API, the official human-in-the-loop middleware, a deterministic local model,
and a mock transfer ledger.

Run one released composition:

```bash
bash experiments/langgraph-agent-server/run_version.sh 0.14.0 1.3.18
```

Run the sampled range or the deny-update safe policy:

```bash
bash experiments/langgraph-agent-server/run_range_matrix.sh
bash experiments/langgraph-agent-server/run_safe_policy.sh
```

The strict oracle requires exact A in the approver's interrupt, denial of maker
resume and direct B, a same-thread A-to-B update through the shipped A2A route,
B at the harmless tool sink under the approver identity, no A on the attack thread,
outsider denial, and an unchanged-A success control.

The safe policy denies the maker's update, leaves A pending, and executes A after
the approver resumes. It is a supported safe composition, not a vendor fix.
Production Postgres is outside this archive.

