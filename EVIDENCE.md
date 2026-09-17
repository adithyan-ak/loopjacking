# Evidence index

This index defines the public evidence set. A directory not listed here is not
part of the reported study.

## Agno AgentOS

The recorded regular-Agent configuration uses a lower-privileged maker, a
distinct admin approver, loopback HTTP, SQLite, a deterministic local model, and a
harmless mock-transfer ledger. The strict trace requires exact A in the approval
record, direct-B denial for the maker, later submission of B through continuation,
and B at the registered tool sink.

| Version | Evidence directory | Interpretation |
|---|---|---|
| 2.5.5 | `evidence/agno-agentos/agno-2.5.5/20260830T205035Z/` | Boundary control: direct B already executes, so the approval is unnecessary |
| 2.5.6 | `evidence/agno-agentos/agno-2.5.6/20260830T205038Z/` | First affected stable release established by the adjacent boundary |
| 2.9.0 | `evidence/agno-agentos/agno-2.9.0/20260830T205029Z/` | Strict positive |
| 3.0.1 | `evidence/agno-agentos/agno-3.0.1/20260830T205032Z/` | Strict positive |
| 3.0.2 | `evidence/agno-agentos/agno-3.0.2/20260830T205101Z/` | Strict positive |
| 3.0.3 | `evidence/agno-agentos/agno-3.0.3/20260830T205355Z/` | Strict positive |
| 3.0.6 | `evidence/agno-agentos/agno-3.0.6/20260907T090624Z/` | Strict positive |
| 3.0.9 | `evidence/agno-agentos/agno-3.0.9/20260910T074852Z/` | Strict positive and evidence-cutoff release |

Each strict-positive bundle reports A-to-B 5/5, unchanged A 5/5, direct-B denial
3/3, a passing role boundary, and 23/23 completed cells. The included exact-action
control is researcher-authored and is not an Agno product fix. The data establishes
only the named versions and configuration; it does not establish every intermediate
patch, deployment prevalence, or a fixed release.

## LangGraph Agent Server

The maker in the tested composition may update a shared pending thread but cannot
resume it or execute B directly. A distinct approver may resume and execute but
does not have the maker's update role. The mutation uses the shipped A2A
`message.command.update` route; the execution uses the official human-in-the-loop
middleware and an in-memory Agent Server.

Native evidence directories:

- `langgraph-api-0.7.4/`: feature-absent boundary control;
- `langgraph-api-0.7.5/`, `0.7.103/`, `0.8.7/`, `0.9.1/`, `0.10.3/`,
  `0.11.4/`, `0.12.4/`, `0.12.6/`, `0.12.9/`, `0.13.2/`, `0.13.4/`, and
  `0.14.0/`: strict-positive sampled releases;
- `langgraph-api-0.13.2-linux-inmem/`: Linux repeat; and
- `langgraph-api-0.13.2-safe-policy/`: deny-update policy blocks B and preserves A.

The two `range-scan*/` directories preserve SHA-256-identified PyPI wheel scans.
They support source continuity from 0.7.5 through 0.13.4. Intermediate patches
that were scanned but not executed must not be described as runtime results.
Version 0.14.0 is a separate executed data point. Production Postgres was not
evaluated, no vendor fix is claimed, and a supported deny-update policy refutes a
universal LangGraph claim.

## OpenClaw

- `openclaw-2026.2.23/20260910T073218Z/`: three affected native trials;
- `openclaw-2026.2.24/20260910T073218Z/`: three fixed native trials; and
- the three May directories plus `advisory-lineage.json`: public-source
  checks reconciling the later overlapping advisory.

On 2026.2.23, the product approval event displayed A while the complete prepared
argv encoded B; B reached the shipped node-host path in 3/3 trials. Direct B was
denied and unchanged approved A succeeded. Version 2026.2.24 rejected the mismatch
before node execution in 3/3 trials while preserving both controls. The canonical
public record is
[GHSA-6rcp-vxwf-3mfp](https://github.com/openclaw/openclaw/security/advisories/GHSA-6rcp-vxwf-3mfp)
/ CVE-2026-32052.

The approval role was scripted only after the exact product event was asserted and
recorded. The experiment tests system binding, not human factors.

## OpenAI Agents SDK

- `evidence/openai-agents-approval-control/openai-agents-0.22.0/20260910T074941Z/`
- `evidence/openai-agents-approval-control/openai-agents-0.22.2/20260910T074929Z/`

For each release, unchanged serialized approved A executed 3/3, same-call-ID raw
invocation mutation to B was rejected 3/3 with no ledger effect, and direct
unapproved B paused. This is a negative control for ordinary per-call approval,
not an OpenAI vulnerability result. Intentional sticky approval and arbitrary
forgery of all canonical serialized state are outside the experiment.

## Archive preparation

The public copies retain the security-relevant requests, approval records,
decisions, results, source hashes, logs, environments, and harmless effects.
Ephemeral local filesystem prefixes and preparation-only labels were removed;
the operation values, trial outcomes, package versions, timestamps, and oracles
were not changed. New SHA-256 manifests bind the public form of every bundle.

Legacy demonstrations, private coordination, disclosure drafts, adjacent
non-approval experiments, manuscript-production records, and unrelated research
are deliberately absent.
