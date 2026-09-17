# OpenClaw representation-binding experiment

This harness tests the shell-wrapper approval path at the released
2026.2.23/2026.2.24 boundary. It uses OpenClaw's loopback gateway, approval
manager, node invocation path, command resolver, and node-host executor. The only
effect is a temporary marker.

Prepare detached OpenClaw worktrees at the desired tags and install each frozen
dependency set with lifecycle scripts disabled:

```bash
corepack pnpm install --frozen-lockfile --ignore-scripts
```

Capture three affected or fixed trials:

```bash
bash experiments/openclaw-approval-binding/capture_version.sh \
  /path/to/openclaw-2026.2.23 1 /path/to/output

bash experiments/openclaw-approval-binding/capture_version.sh \
  /path/to/openclaw-2026.2.24 0 /path/to/output
```

The affected oracle requires exact approval of displayed A, release and execution
of the already-prepared complete argv B, denial of direct B, and success of
unchanged A. The fixed oracle requires the A/B mismatch to be rejected before node
execution while the controls still pass.

`capture_range.sh` performs the narrower source check used to reconcile the
overlapping May advisory record. It does not execute a command.

