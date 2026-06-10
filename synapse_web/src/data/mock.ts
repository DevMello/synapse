// Synapse Web UI — mock data (a busy fleet). Typed port of the design prototype's
// data.js. Reached only through the TanStack hooks in src/api/queries.ts, which is
// where real REST / Supabase calls drop in later.
import type {
  Agent, Alert, Approval, Capability, CapabilityDef, Daemon, EnvVar, LogLine,
  MemoryEntry, Org, OrgSummary, Run, Skill, Template, TraceLine, Version,
} from "../types";

export const ORG: Org = { id: "personal", name: "northwind", plan: "Team", operator: "Avery Koss", initials: "AK" };

export const ORGS: OrgSummary[] = [{ id: "personal", name: "northwind", plan: "Team", initials: "AK", isPersonal: true }];

const CAP_DEFS: CapabilityDef[] = [
  { id: "fs", name: "filesystem", kind: "MCP server", desc: "Scoped file read/write tools", builtin: true },
  { id: "fetch", name: "fetch", kind: "MCP server", desc: "HTTP fetch with allow-list", builtin: true },
  { id: "git", name: "git", kind: "MCP server", desc: "Repo status, diff, commit, branch", builtin: true },
  { id: "memory", name: "memory", kind: "MCP server", desc: "Persistent agent memory store", builtin: true },
  { id: "github", name: "github", kind: "MCP server", desc: "PRs, issues, reviews", builtin: false },
  { id: "playwright", name: "browser use", kind: "plugin", desc: "Playwright browser automation", builtin: false },
  { id: "shell", name: "terminal use", kind: "plugin", desc: "Sandboxed shell", builtin: false },
  { id: "postgres", name: "postgres", kind: "MCP server", desc: "Read-only SQL", builtin: false },
  { id: "slack", name: "slack", kind: "MCP server", desc: "Post + read channels", builtin: false },
];

// Deterministic per-daemon capability state (no Math.random — stable renders).
const READY_BY_DAEMON: Record<string, string[]> = {
  "d-mbp": ["fs", "fetch", "git", "memory", "github", "playwright"],
  "d-ci": ["fs", "fetch", "git", "memory", "github", "shell", "postgres"],
  "d-edge": ["fs", "fetch", "git", "memory", "slack"],
  "d-win": ["fs", "fetch", "git", "memory"],
};
function capsFor(daemonId: string): Capability[] {
  const ready = READY_BY_DAEMON[daemonId] ?? [];
  return CAP_DEFS.map((c) => ({
    ...c,
    state: c.builtin || ready.includes(c.id)
      ? "ready"
      : daemonId === "d-mbp" && c.id === "postgres"
        ? "installing"
        : "available",
  }));
}

const daemonsBase: Omit<Daemon, "capabilities">[] = [
  { id: "d-mbp", name: "my-macbook-pro", hostname: "my-macbook-pro.local", os: "macOS 15.3", ip: "192.168.1.24",
    status: "online", version: "synapsed 1.4.2", lastSeen: "2 min ago", cpu: 38, mem: 61, activeRuns: 2,
    uptime: 99.98, tags: ["laptop", "apple-silicon"], platform: "darwin/arm64", heartbeat: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] },
  { id: "d-ci", name: "ci-runner-04", hostname: "ci-runner-04", os: "Ubuntu 22.04 LTS", ip: "10.0.4.18",
    status: "online", version: "synapsed 1.4.2", lastSeen: "just now", cpu: 72, mem: 54, activeRuns: 3,
    uptime: 99.91, tags: ["ci", "linux", "gpu"], platform: "linux/amd64", heartbeat: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] },
  { id: "d-edge", name: "edge-box-sf", hostname: "edge-box-sf", os: "Debian 12", ip: "73.202.88.10",
    status: "online", version: "synapsed 1.4.1", lastSeen: "40 sec ago", cpu: 21, mem: 33, activeRuns: 1,
    uptime: 99.62, tags: ["edge", "linux"], platform: "linux/amd64", heartbeat: [1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1] },
  { id: "d-win", name: "studio-win", hostname: "studio-win", os: "Windows 11 Pro", ip: "192.168.1.51",
    status: "offline", version: "synapsed 1.3.9", lastSeen: "3 hr ago", cpu: 0, mem: 0, activeRuns: 0,
    uptime: 94.2, tags: ["workstation", "windows"], platform: "windows/amd64", heartbeat: [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0] },
];

export const daemons: Daemon[] = daemonsBase.map((d) => ({ ...d, capabilities: capsFor(d.id) }));

export const PROMPT = `# pr-reviewer — system prompt

You are a senior code reviewer operating on the **northwind** monorepo.
Review the diff in the current pull request and leave precise, actionable comments.

## Operating rules
- Read \`reports/style-guide.md\` before commenting on style.
- Never approve a PR that drops test coverage below {{min_coverage}}%.
- Flag any new network call that is not on the allow-list.
- Summarize findings in \`reports/review/{{pr_number}}.md\`.

## Voice
Direct, specific, kind. Cite file paths and line numbers. No filler.

## Variables
- {{min_coverage}} — minimum coverage gate (default 80)
- {{pr_number}} — the PR under review`;

export const versions: Version[] = [
  { id: "v12", label: "v12", author: "Avery Koss", when: "2 hr ago", msg: "Tighten coverage gate to 80%", tags: ["production"], current: true },
  { id: "v11", label: "v11", author: "Avery Koss", when: "yesterday", msg: "Add network allow-list rule", tags: ["known-good"] },
  { id: "v10", label: "v10", author: "Jin Park", when: "3 days ago", msg: "Rewrite voice section", tags: [] },
  { id: "v9", label: "v9", author: "Avery Koss", when: "5 days ago", msg: "Initial review ruleset", tags: [] },
];

export const traceLines: TraceLine[] = [
  { t: "cmd", text: "pr-reviewer · run #2214", comment: "trigger: webhook · PR #2214" },
  { t: "info", text: "plan: 4 steps — read diff, check coverage, scan network calls, write report" },
  { t: "info", text: "host: my-macbook-pro · keys stay local" },
  { t: "ok", text: "read: 14 files changed (+612 / −188)" },
  { t: "ok", text: "mcp:git diff resolved · 3 modules touched" },
  { t: "warn", text: "coverage: 78.4% — below gate (80%)" },
  { t: "info", text: "tool:fetch blocked — api.unknown-vendor.com not on allow-list" },
  { t: "ok", text: "redaction: masked 1 secret before upload" },
];

export const agents: Agent[] = [
  { id: "a-prr", name: "pr-reviewer", type: "CLI tool", engine: "Claude Code", daemonId: "d-mbp",
    status: "running", avail: true, lastRun: "2 min ago", nextRun: "on webhook", spendToday: 4.82,
    runsTotal: 1284, errRate: 2.1, tokensToday: 1840000, model: "claude-sonnet-4",
    desc: "Reviews every PR against the northwind ruleset and writes a report." },
  { id: "a-cdx", name: "codex-builder", type: "CLI tool", engine: "Codex", daemonId: "d-ci",
    status: "running", avail: true, lastRun: "just now", nextRun: "02:00 nightly", spendToday: 11.4,
    runsTotal: 642, errRate: 4.0, tokensToday: 3120000, model: "gpt-5-codex",
    desc: "Implements scoped tickets and opens PRs on the build queue." },
  { id: "a-sup", name: "support-triage", type: "API model", engine: "API", daemonId: "d-edge",
    status: "running", avail: true, lastRun: "12 sec ago", nextRun: "on webhook", spendToday: 2.16,
    runsTotal: 5821, errRate: 0.8, tokensToday: 940000, model: "claude-sonnet-4",
    desc: "Triages inbound tickets, drafts replies, escalates with HITL." },
  { id: "a-doc", name: "doc-writer", type: "CLI tool", engine: "Gemini CLI", daemonId: "d-ci",
    status: "idle", avail: true, lastRun: "1 hr ago", nextRun: "06:00 daily", spendToday: 0.74,
    runsTotal: 210, errRate: 1.4, tokensToday: 220000, model: "gemini-2.5-pro",
    desc: "Keeps the docs site in sync with shipped changes." },
  { id: "a-bf", name: "data-backfill", type: "API model", engine: "API", daemonId: "d-mbp",
    status: "passed", avail: true, lastRun: "20 min ago", nextRun: "manual", spendToday: 0.31,
    runsTotal: 88, errRate: 0.0, tokensToday: 60000, model: "claude-haiku-4",
    desc: "One-shot backfill jobs over the analytics warehouse." },
  { id: "a-rel", name: "release-notes", type: "API model", engine: "API", daemonId: "d-win",
    status: "offline", avail: false, lastRun: "3 hr ago", nextRun: "host offline", spendToday: 0.0,
    runsTotal: 156, errRate: 3.2, tokensToday: 0, model: "claude-sonnet-4",
    desc: "Drafts release notes from the merged-PR log each Friday." },
];

export const runs: Run[] = [
  { id: "r2214", agentId: "a-prr", agent: "pr-reviewer", trigger: "webhook", status: "running", started: "2 min ago", dur: "—", cost: 0.41, tokens: 92000, exit: "—" },
  { id: "r2213", agentId: "a-cdx", agent: "codex-builder", trigger: "schedule", status: "running", started: "6 min ago", dur: "—", cost: 2.1, tokens: 410000, exit: "—" },
  { id: "r2212", agentId: "a-sup", agent: "support-triage", trigger: "webhook", status: "running", started: "12 sec ago", dur: "—", cost: 0.04, tokens: 8200, exit: "—" },
  { id: "r2211", agentId: "a-prr", agent: "pr-reviewer", trigger: "webhook", status: "blocked", started: "18 min ago", dur: "1m 42s", cost: 0.22, tokens: 51000, exit: "gate" },
  { id: "r2210", agentId: "a-bf", agent: "data-backfill", trigger: "manual", status: "passed", started: "20 min ago", dur: "3m 08s", cost: 0.31, tokens: 60000, exit: "0" },
  { id: "r2209", agentId: "a-cdx", agent: "codex-builder", trigger: "schedule", status: "passed", started: "42 min ago", dur: "11m 20s", cost: 4.8, tokens: 980000, exit: "0" },
  { id: "r2208", agentId: "a-prr", agent: "pr-reviewer", trigger: "webhook", status: "recovering", started: "1 hr ago", dur: "—", cost: 0.18, tokens: 39000, exit: "—" },
  { id: "r2207", agentId: "a-doc", agent: "doc-writer", trigger: "schedule", status: "passed", started: "1 hr ago", dur: "2m 51s", cost: 0.74, tokens: 220000, exit: "0" },
];

export const approvals: Approval[] = [
  { id: "ap-1", agentId: "a-cdx", agent: "codex-builder", daemon: "ci-runner-04", severity: "block",
    action: "Force-push to protected branch", command: "git push --force origin main",
    reason: "Rebase resolved 3 conflicts; history was rewritten to keep a linear log. Force-push needed to update the remote.",
    context: "12 commits · main ← feature/payment-retries", when: "3 min ago" },
  { id: "ap-2", agentId: "a-sup", agent: "support-triage", daemon: "edge-box-sf", severity: "require-approval",
    action: "Send refund via Stripe API", command: "POST /v1/refunds  amount=4200 currency=usd",
    reason: "Customer #88213 reported a duplicate charge; the duplicate transaction is confirmed in the ledger. Issuing a full refund of $42.00.",
    context: "ticket #5521 · customer #88213", when: "8 min ago" },
  { id: "ap-3", agentId: "a-prr", agent: "pr-reviewer", daemon: "my-macbook-pro", severity: "require-approval",
    action: "Delete files outside repo root", command: "rm -rf ~/.cache/northwind/tmp",
    reason: "Cleanup step wants to remove a stale 2.1 GB cache dir. Path is outside the repo guard, so it needs approval.",
    context: "run #2211 · path guard tripped", when: "18 min ago" },
];

export const alerts: Alert[] = [
  { id: "al-1", type: "prompt-injection", icon: "shield-alert", sev: "warn", title: "Prompt-injection spike on support-triage",
    metric: "override attempts", baseline: "0–1 / hr", observed: "14 / hr", agent: "support-triage", when: "5 min ago",
    detail: "Inbound ticket content repeatedly tried to override instructions. 14 blocked, agent auto-paused pending review." },
  { id: "al-2", type: "offline", icon: "wifi-off", sev: "warn", title: "Daemon offline: studio-win",
    metric: "last heartbeat", baseline: "< 30 sec", observed: "3 hr ago", agent: "studio-win", when: "3 hr ago",
    detail: "No heartbeat from studio-win for 3 hours. 1 agent (release-notes) is unavailable." },
  { id: "al-3", type: "cost", icon: "trending-up", sev: "info", title: "Cost-per-task 2.4× baseline on codex-builder",
    metric: "cost / task", baseline: "$0.84", observed: "$2.01", agent: "codex-builder", when: "34 min ago",
    detail: "Nightly build run is replanning more than usual. Drill into run #2209 for the trace." },
];

export const envVars: EnvVar[] = [
  { key: "OPENAI_API_KEY", secret: true, origin: "cloud", updated: "2 hr ago", by: "AK" },
  { key: "GITHUB_TOKEN", secret: true, origin: "cloud", updated: "yesterday", by: "AK" },
  { key: "DATABASE_URL", secret: true, origin: "cloud", updated: "3 days ago", by: "Jin Park" },
  { key: "LOG_LEVEL", secret: false, value: "info", origin: "cloud", updated: "3 days ago", by: "AK" },
  { key: "NORTHWIND_ENV", secret: false, value: "production", origin: "cloud", updated: "1 wk ago", by: "AK" },
  { key: "SSH_AGENT_PID", secret: true, origin: "local", updated: "set on daemon", by: "—" },
];

export const memory: MemoryEntry[] = [
  { key: "style/line-length", ns: "rules", val: "Max line length is 100 chars in the northwind monorepo.", tags: ["style"], size: "0.2 KB", updated: "2 hr ago" },
  { key: "fact/ci-provider", ns: "facts", val: "CI runs on ci-runner-04 via the build queue, not GitHub Actions.", tags: ["infra"], size: "0.3 KB", updated: "yesterday" },
  { key: "pref/review-tone", ns: "prefs", val: "Reviewers prefer questions over directives for non-blocking nits.", tags: ["voice"], size: "0.2 KB", updated: "3 days ago" },
  { key: "fact/coverage-tool", ns: "facts", val: "Coverage is measured by vitest --coverage, reported as a single %.", tags: ["testing"], size: "0.2 KB", updated: "4 days ago" },
  { key: "fact/allow-list", ns: "facts", val: "Network allow-list lives in reports/allow-list.txt; one host per line.", tags: ["security"], size: "0.3 KB", updated: "5 days ago" },
];

export const logLines: LogLine[] = [
  { time: "02:31:08", tag: "plan", msg: "decomposed PR #2214 into 4 steps" },
  { time: "02:31:09", tag: "build", msg: "read 14 files changed (+612 / −188)" },
  { time: "02:31:14", tag: "qa", msg: "coverage 78.4% — below gate" },
  { time: "02:31:15", tag: "mcp", msg: "tool:fetch blocked — api.unknown-vendor.com", guard: "tool-bypass" },
  { time: "02:31:16", tag: "mcp", msg: "redacted <REDACTED:API_KEY> before upload" },
  { time: "02:31:18", tag: "plan", msg: "wrote reports/review/2214.md" },
];

export const skills: Skill[] = [
  { name: "review-checklist", scope: "all platforms", size: "4.1 KB" },
  { name: "security-scan", scope: "macOS · Linux", size: "2.8 KB" },
  { name: "win-codesign", scope: "Windows", size: "1.2 KB" },
];

export const templates: Template[] = [
  { id: "blank", name: "Blank agent", desc: "Start from an empty prompt.", kicker: "TEMPLATE", icon: "file-text" },
  { id: "reviewer", name: "PR reviewer", desc: "Reviews diffs against a ruleset, writes a report.", kicker: "MARKETPLACE", icon: "git-pull-request", rating: 4.8 },
  { id: "triage", name: "Support triage", desc: "Triages tickets, drafts replies, escalates with HITL.", kicker: "MARKETPLACE", icon: "inbox", rating: 4.6 },
  { id: "builder", name: "Ticket builder", desc: "Implements scoped tickets and opens PRs.", kicker: "MARKETPLACE", icon: "code", rating: 4.7 },
];

export { CAP_DEFS };
