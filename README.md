# Loopjacking evidence archive

This repository contains the public evidence and reproduction harnesses for
*Loopjacking: Hijacking Human-in-the-Loop Approval*.

Loopjacking is an implementation-level failure in which a human approves the
operation or representation they understand as A, but product-owned logic uses
that decision to authorize or release materially different B. The archive covers
two variants: representation mismatch before approval and state substitution
after approval.

## What is included

| Product path | Role in the study | Recorded result |
|---|---|---|
| Agno AgentOS regular-Agent approval | Post-approval state substitution | Strict traces on the tested configurations from 2.5.6 through the sampled 3.0.9 release; 2.5.5 is the direct-B boundary control |
| LangGraph Agent Server with the declared Auth policy | Conditional post-approval state substitution | Native positives on the sampled in-memory releases from 0.7.5 through 0.14.0; 0.7.4 is feature-absent and a deny-update policy is safe |
| OpenClaw shell-wrapper approval | Representation-based case | 2026.2.23 reproduces the mismatch; 2026.2.24 rejects it |
| OpenAI Agents SDK ordinary per-call approval | Negative control | 0.22.0 and 0.22.2 reject same-call-ID A-to-B mutation while executing unchanged A |

The experiments use loopback services, synthetic principals, deterministic local
models, and harmless recording sinks. They do not contact production agents,
payment systems, customer data, or model providers.

See [EVIDENCE.md](EVIDENCE.md) for the exact bundles, controls, claim boundaries,
and limitations.

## Verify the recorded archive

Python 3.10 or later is sufficient for the read-only verifier:

```bash
python3 verify_archive.py
```

The verifier checks the archive-wide and per-bundle SHA-256 manifests, confirms
the recorded result oracles, enforces the documented bundle set, and scans for
private path fragments and preparation residue.

## Reproduce an experiment

Each harness has its own instructions:

- [Agno AgentOS](experiments/agno-agentos/README.md)
- [LangGraph Agent Server](experiments/langgraph-agent-server/README.md)
- [OpenClaw](experiments/openclaw-approval-binding/README.md)
- [OpenAI Agents SDK](experiments/openai-agents-approval-control/README.md)

Reruns create new timestamped evidence. They require network access only when the
pinned public packages or dependencies are not already cached. Review a harness
before running it and use an isolated local environment.

## Scope

This is a purposive comparative archive, not a prevalence survey. The evidence
does not establish that all versions, deployments, agent frameworks, or A2A
implementations are vulnerable. It does not assign a universal CWE, CVSS score,
or affected-version range. Agno and LangGraph have no vendor-fixed release in this
archive. LangGraph's result is conditional on the tested in-memory composition and
authorization policy. The OpenClaw approval role was scripted after the harness
asserted the exact product approval event, so that experiment does not measure
human comprehension or GUI behavior. All runs were operated by one researcher;
independent reproduction is not claimed.

The evidence cutoff is September 10, 2026.

## Citation

Until the paper has a final archival identifier, cite the paper title and this
repository URL. A formal citation record can be added once the preprint identifier
is assigned.
