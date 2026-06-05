// Agent Detail — Tools & MCP tab. Agent-tier capability selection (attach/detach
// from what the host daemon already has), rulesets & blockers, and content
// filtering / guardrails. Ported from the prototype's ToolsTab (AgentTabs2.jsx).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, Chip } from "../../../components/Primitives";
import { Toggle, Segmented, daemonName, type SegOption } from "../../../components/Common";
import { data } from "../../../api/queries";
import { useUI } from "../../../store/ui";
import { useCurrentAgent } from "../context";
import type { Capability, Severity } from "../../../types";

type SubTab = "caps" | "blockers" | "filter";

export default function ToolsTab() {
  const [sub, setSub] = useState<SubTab>("caps");
  const subs: { id: SubTab; name: string }[] = [
    { id: "caps", name: "Capabilities" },
    { id: "blockers", name: "Rulesets & blockers" },
    { id: "filter", name: "Filtering" },
  ];
  return (
    <div className="db-tools">
      <div className="db-subtabs">
        {subs.map((s) => (
          <button
            key={s.id}
            className={"db-subtab" + (sub === s.id ? " active" : "")}
            onClick={() => setSub(s.id)}
          >
            {s.name}
          </button>
        ))}
      </div>
      {sub === "caps" && <CapabilitiesPanel />}
      {sub === "blockers" && <BlockersPanel />}
      {sub === "filter" && <FilteringPanel />}
    </div>
  );
}

function CapabilitiesPanel() {
  const agent = useCurrentAgent();
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const daemon = data.daemons.find((d) => d.id === agent.daemonId);
  const installed: Capability[] = daemon ? daemon.capabilities : [];

  // Local attach/detach selection. Built-in defaults are on; github is attached
  // by default to mirror the prototype's seeded state.
  const [attached, setAttached] = useState<Record<string, boolean>>(() => {
    const m: Record<string, boolean> = {};
    data.CAP_DEFS.forEach((c) => {
      m[c.id] = c.builtin && c.id !== "fetch" ? true : c.id === "github";
    });
    m.fetch = true;
    return m;
  });

  return (
    <>
      <div className="db-callout">
        <Icon name="layers" size={16} />
        <span>
          <b>Agent tier.</b> Toggle what this agent may use from the capabilities already
          installed on{" "}
          <button className="db-inline-link" onClick={() => navigate("/daemons")}>
            {daemonName(agent.daemonId)}
          </button>
          . Toggling is instant — it attaches/detaches, it doesn't install or tear down.
        </span>
      </div>
      <div className="db-cap-list">
        {data.CAP_DEFS.map((c) => {
          const onHost = installed.find((x) => x.id === c.id);
          const ready = onHost && onHost.state === "ready";
          const installing = onHost && onHost.state === "installing";
          return (
            <div key={c.id} className={"db-cap-attach" + (!ready ? " unavailable" : "")}>
              <span className={"db-cap-attach-icon" + (attached[c.id] && ready ? " on" : "")}>
                <Icon name={c.kind === "plugin" ? "puzzle" : "plug"} size={15} />
              </span>
              <div className="db-cap-attach-meta">
                <div className="db-cap-attach-name">
                  {c.name}
                  {c.builtin && <span className="db-cap-default">default</span>}
                </div>
                <div className="db-cap-attach-desc">
                  {c.kind} · {c.desc}
                </div>
              </div>
              {ready ? (
                <Toggle
                  on={!!attached[c.id]}
                  onChange={(v) => {
                    setAttached((p) => ({ ...p, [c.id]: v }));
                    showToast({
                      text: `${c.name} ${v ? "attached to" : "detached from"} ${agent.name}`,
                    });
                  }}
                />
              ) : installing ? (
                <span className="db-cap-state installing">
                  <span className="db-spin" /> installing
                </span>
              ) : (
                <button className="db-cap-install-hint" onClick={() => navigate("/daemons")}>
                  Install on daemon <Icon name="arrow-up-right" size={12} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <div className="db-gateways">
        <div className="db-sublabel">Gateways</div>
        <div className="db-gateway-row">
          <span className="db-mono">
            <Icon name="globe" size={13} /> anthropic-proxy.northwind.internal
          </span>
          <Chip s="ready" label="active" />
        </div>
      </div>
    </>
  );
}

interface Rule {
  id: string;
  name: string;
  pattern: string;
  sev: Severity;
  icon: string;
}

const RULES: Rule[] = [
  { id: "r1", name: "Force-push to protected branch", pattern: "git push --force", sev: "require-approval", icon: "git-branch" },
  { id: "r2", name: "Delete outside repo root", pattern: "rm -rf <path not in repo>", sev: "require-approval", icon: "trash" },
  { id: "r3", name: "Network allow-list", pattern: "only hosts in reports/allow-list.txt", sev: "block", icon: "globe" },
  { id: "r4", name: "Production secrets in shell", pattern: "echo $*_SECRET / $*_KEY", sev: "block", icon: "key" },
  { id: "r5", name: "Cost cap per run", pattern: "> $8.00 / run", sev: "warn", icon: "dollar-sign" },
  { id: "r6", name: "Tool-call cap", pattern: "> 200 tool calls / run", sev: "warn", icon: "sliders" },
];

function BlockersPanel() {
  const showToast = useUI((s) => s.showToast);
  const [rules, setRules] = useState<Rule[]>(RULES);
  const SEV: SegOption<Severity>[] = [
    { value: "block", label: "Block" },
    { value: "require-approval", label: "Approve" },
    { value: "warn", label: "Warn" },
  ];
  return (
    <>
      <div className="db-callout">
        <Icon name="shield" size={16} />
        <span>
          <b>Enforcement surface.</b> Each rule fires on the daemon before a command runs.
          Severity decides what happens: <span className="db-sev-pill block">block</span>{" "}
          <span className="db-sev-pill require-approval">require approval</span>{" "}
          <span className="db-sev-pill warn">warn</span>.
        </span>
      </div>
      <div className="db-rule-list">
        {rules.map((r) => (
          <div key={r.id} className="db-rule-row">
            <span className="db-rule-icon">
              <Icon name={r.icon} size={15} />
            </span>
            <div className="db-rule-meta">
              <div className="db-rule-name">{r.name}</div>
              <div className="db-rule-pattern db-mono">{r.pattern}</div>
            </div>
            <Segmented
              value={r.sev}
              onChange={(v) =>
                setRules((rs) => rs.map((x) => (x.id === r.id ? { ...x, sev: v } : x)))
              }
              options={SEV}
            />
          </div>
        ))}
      </div>
      <button className="db-add-row" onClick={() => showToast({ text: "Add a custom rule" })}>
        <Icon name="plus" size={14} /> Add rule
      </button>
    </>
  );
}

type DetMode = "hash" | "mask" | "block";
interface Detector {
  id: string;
  name: string;
  mode: DetMode;
}

function FilteringPanel() {
  const [detectors, setDetectors] = useState<Record<string, boolean>>({
    apikey: true, email: true, token: true, card: true, ssn: false,
  });
  const [inbound, setInbound] = useState(true);
  const [outbound, setOutbound] = useState(true);
  const [classifier, setClassifier] = useState(true);
  const DET: Detector[] = [
    { id: "apikey", name: "API keys", mode: "hash" },
    { id: "email", name: "Email addresses", mode: "mask" },
    { id: "token", name: "Bearer / OAuth tokens", mode: "hash" },
    { id: "card", name: "Card / SSN patterns", mode: "block" },
    { id: "ssn", name: "Custom: employee IDs", mode: "mask" },
  ];
  const findings: [string, Severity][] = [
    ["override", "block"],
    ["exfiltration", "block"],
    ["tool-bypass", "require-approval"],
    ["policy-divergence", "warn"],
  ];
  return (
    <>
      <div className="db-callout">
        <Icon name="eye-off" size={16} />
        <span>
          <b>Daemon-side guardrails.</b> Content is screened on the host before it reaches the
          model and before output leaves. Overrides sit on top of the org-wide default policy.{" "}
          <span className="db-inherited">3 inherited</span> ·{" "}
          <span className="db-overridden">2 overridden</span>.
        </span>
      </div>

      <div className="db-filter-grid">
        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">PII / secret redaction</h3>
          </div>
          <div className="db-det-list">
            {DET.map((dt) => (
              <div key={dt.id} className="db-det-row">
                <Toggle
                  on={!!detectors[dt.id]}
                  onChange={(v) => setDetectors((p) => ({ ...p, [dt.id]: v }))}
                />
                <span className="db-det-name">{dt.name}</span>
                <span className={"db-mode-pill " + dt.mode}>{dt.mode}</span>
              </div>
            ))}
          </div>
          <div className="db-filter-note db-mono">
            <Icon name="lock" size={12} /> Tokens are salted on-device — the cloud never sees
            plaintext.
          </div>
        </div>

        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">Prompt-injection &amp; jailbreak guard</h3>
          </div>
          <div className="db-guard-toggle">
            <Toggle on={inbound} onChange={setInbound} />
            <div>
              <div className="db-guard-name">Inbound screening</div>
              <div className="db-guard-desc">
                Untrusted tool/web content checked for override, exfiltration, tool-bypass.
              </div>
            </div>
          </div>
          <div className="db-guard-toggle">
            <Toggle on={outbound} onChange={setOutbound} />
            <div>
              <div className="db-guard-name">Outbound screening</div>
              <div className="db-guard-desc">
                Model output checked for self-instruction override, policy divergence, secret-leak.
              </div>
            </div>
          </div>
          <div className="db-guard-toggle">
            <Toggle on={classifier} onChange={setClassifier} />
            <div>
              <div className="db-guard-name">
                Local classifier <span className="db-mono db-muted">(Ollama)</span>
              </div>
              <div className="db-guard-desc">On-device model. Available on this host.</div>
            </div>
          </div>
          <div className="db-finding-map">
            <div className="db-sublabel">Finding → action</div>
            {findings.map(([cat, act]) => (
              <div key={cat} className="db-finding-row db-mono">
                <span>{cat}</span>
                <span className={"db-sev-pill " + act}>
                  {act.replace("require-approval", "approve")}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
