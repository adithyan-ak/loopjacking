import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

async function main() {
  const targetRoot = process.env.OPENCLAW_ROOT;
  if (!targetRoot) {
    throw new Error("OPENCLAW_ROOT is required");
  }

  const packageJson = JSON.parse(
    fs.readFileSync(path.join(targetRoot, "package.json"), "utf8"),
  ) as { version?: string };
  const moduleUrl = pathToFileURL(
    path.join(targetRoot, "src", "infra", "system-run-command.ts"),
  ).href;
  const { formatExecCommand, resolveSystemRunCommand } = (await import(moduleUrl)) as {
    formatExecCommand: (argv: string[]) => string;
    resolveSystemRunCommand: (input: {
      command: string[];
      rawCommand?: string;
    }) => Record<string, unknown>;
  };

  const visibleA = '$0 "$1"';
  const command = [
    "/bin/sh",
    "-lc",
    visibleA,
    "/usr/bin/touch",
    "/tmp/openclaw-loopjacking-range-probe.marker",
  ];
  const result = {
    packageVersion: packageJson.version ?? null,
    targetRoot,
    visibleA,
    completeUnderlyingRequest: command,
    canonicalOperationB: formatExecCommand(command),
    productResolutionWithRawA: resolveSystemRunCommand({ command, rawCommand: visibleA }),
    productDerivedApprovalTextWithoutRaw: resolveSystemRunCommand({ command }),
    executed: false,
  };

  console.log(`OPENCLAW_RANGE_RESULT=${JSON.stringify(result)}`);
}

void main();
