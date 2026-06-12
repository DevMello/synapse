// Seed data for the Model Comparison screens in mock/offline mode (§10). Mirrors the way
// screens/flow/templates.ts backs the Flow Canvas offline so the comparison UI is fully
// interactive without a live backend.
import type {
  AvailableModel,
  ComparisonVariant,
  RunGroup,
} from "../../types";
import type { LaunchArgs } from "../../api/queries/comparisons";

export const MOCK_MODELS: AvailableModel[] = [
  { model: "claude-opus-4-8", provider: "anthropic", inputPerMtok: 5, outputPerMtok: 25, hasCredentials: true, estimateUsd: 0.0275 },
  { model: "claude-sonnet-4-6", provider: "anthropic", inputPerMtok: 3, outputPerMtok: 15, hasCredentials: true, estimateUsd: 0.0165 },
  { model: "gpt-5", provider: "openai", inputPerMtok: 10, outputPerMtok: 30, hasCredentials: true, estimateUsd: 0.039 },
  { model: "gpt-5-mini", provider: "openai", inputPerMtok: 0.5, outputPerMtok: 1.5, hasCredentials: false, estimateUsd: 0.00195 },
  { model: "gemini-2-pro", provider: "google", inputPerMtok: 1.25, outputPerMtok: 5, hasCredentials: true, estimateUsd: 0.005875 },
  { model: "gemini-2-flash", provider: "google", inputPerMtok: 0.15, outputPerMtok: 0.6, hasCredentials: true, estimateUsd: 0.000705 },
];

let _n = 0;
function uid(prefix: string): string {
  _n += 1;
  const rnd =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : `${Date.now().toString(16)}${_n}`;
  return `${prefix}_${rnd}`;
}

function variant(
  model: string,
  output: string,
  cost: number,
  tin: number,
  tout: number,
  latency: number,
  proposed: { name: string; argsRedacted: unknown; hitl: boolean }[] = [],
): ComparisonVariant {
  return {
    runId: uid("rn"),
    model,
    status: "succeeded",
    costUsd: cost,
    tokensIn: tin,
    tokensOut: tout,
    latencyMs: latency,
    output,
    error: null,
    toolCalls: proposed.map((p) => ({ name: p.name, simulated: true })),
    proposedActions: proposed,
    simulatedHitl: proposed.filter((p) => p.hitl).map((p) => ({ name: p.name, argsRedacted: p.argsRedacted })),
    isWinner: false,
  };
}

export function seedMockComparisons(): RunGroup[] {
  return [
    {
      id: "grp_demo1",
      agentId: "agt_triage",
      status: "ready_for_review",
      models: ["claude-opus-4-8", "gpt-5", "gemini-2-pro"],
      totalCostUsd: 0.0721,
      groupCostCap: 1.0,
      winnerRunId: null,
      created: "12m ago",
      variants: [
        variant(
          "claude-opus-4-8",
          "Categorized the ticket as `billing/refund`, drafted a concise reply, and flagged it for a refund under $20.",
          0.0275, 1480, 760, 5210,
          [{ name: "send_email", argsRedacted: { to: "<REDACTED:EMAIL:9a1f>", subject: "Re: refund" }, hitl: false }],
        ),
        variant(
          "gpt-5",
          "Classified as billing. Suggested issuing a refund and asked a clarifying question before acting.",
          0.039, 1505, 905, 4120,
          [
            { name: "send_email", argsRedacted: { to: "<REDACTED:EMAIL:9a1f>" }, hitl: false },
            { name: "issue_refund", argsRedacted: { amount: 18 }, hitl: true },
          ],
        ),
        variant(
          "gemini-2-pro",
          "Tagged billing/refund and produced a short reply. Did not propose any side-effecting action.",
          0.0059, 1460, 470, 2980,
        ),
      ],
    },
    {
      id: "grp_demo2",
      agentId: "agt_triage",
      status: "running",
      models: ["claude-sonnet-4-6", "gpt-5-mini"],
      totalCostUsd: 0,
      groupCostCap: null,
      winnerRunId: null,
      created: "just now",
      variants: [
        { ...variant("claude-sonnet-4-6", "", 0, 0, 0, 0), status: "running", output: "" },
        { ...variant("gpt-5-mini", "", 0, 0, 0, 0), status: "running", output: "" },
      ],
    },
  ];
}

// A mock launch fabricates a ready-to-review group so the offline demo shows results.
export function mockLaunch(args: LaunchArgs): RunGroup {
  const variants = args.models.map((m, i) =>
    variant(
      m,
      `(${m}) produced a result for the pinned task.`,
      0.01 + i * 0.004,
      1400 + i * 30,
      500 + i * 60,
      2500 + i * 700,
      i % 2 === 1 ? [{ name: "send_email", argsRedacted: { to: "<REDACTED:EMAIL:dr1f>" }, hitl: false }] : [],
    ),
  );
  return {
    id: uid("grp"),
    agentId: args.agentId,
    status: "ready_for_review",
    models: args.models,
    totalCostUsd: variants.reduce((s, v) => s + v.costUsd, 0),
    groupCostCap: args.groupCostCap ?? null,
    winnerRunId: null,
    created: "just now",
    variants,
  };
}
