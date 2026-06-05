// Marketplace — browse the Agent / Skill / Plugin catalogs and one-click install.
// Ported from the prototype's Marketplace view (design-reference/app/Views.jsx) and
// built to full depth per docs/web-ui.md §4.14: a segmented kind switch, search,
// listing cards with platform compatibility, required tools/MCP, requested
// permissions, version + ratings, and an install flow (agents open the New Agent
// wizard; skills/plugins provision onto a chosen target daemon with a toast).
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Icon } from "../components/Primitives";
import { Modal, PageHead, Segmented } from "../components/Common";
import { useUI } from "../store/ui";
import { useDaemons } from "../api/queries";

type Kind = "Agent" | "Skill" | "Plugin";

interface Listing {
  name: string;
  kind: Kind;
  desc: string;
  icon: string;
  plat: string;
  version: string;
  rating: number;
  installs: string;
  // Capabilities the listing needs on the target daemon, and the permissions it asks for.
  requires: string[];
  permissions: string[];
}

// On-brand catalog, synthesized per kind in the busy-fleet voice. Concrete names,
// realistic compatibility and permission scopes — no filler.
const CATALOG: Listing[] = [
  // ── Agents ──────────────────────────────────────────────────────────────
  {
    name: "pr-reviewer", kind: "Agent", icon: "git-pull-request",
    desc: "Reviews diffs against a ruleset, posts inline comments, and writes a verdict report.",
    plat: "macOS · Linux", version: "2.3.1", rating: 4.8, installs: "12.4k",
    requires: ["github", "Claude Code"], permissions: ["repo:read", "pr:write"],
  },
  {
    name: "support-triage", kind: "Agent", icon: "inbox",
    desc: "Triages inbound tickets, drafts replies, and escalates the hard ones via HITL.",
    plat: "all", version: "1.9.0", rating: 4.6, installs: "8.1k",
    requires: ["zendesk", "slack"], permissions: ["tickets:write", "hitl:request"],
  },
  {
    name: "release-captain", kind: "Agent", icon: "zap",
    desc: "Cuts release branches, runs the gate, drafts changelogs, and tags on green.",
    plat: "Linux", version: "0.8.4", rating: 4.4, installs: "2.7k",
    requires: ["github", "Codex"], permissions: ["repo:write", "ci:trigger"],
  },
  {
    name: "incident-commander", kind: "Agent", icon: "alert-triangle",
    desc: "Watches alerts, opens a war-room thread, gathers context, and proposes a rollback.",
    plat: "all", version: "1.2.0", rating: 4.7, installs: "4.3k",
    requires: ["pagerduty", "slack", "postgres"], permissions: ["alerts:read", "deploy:rollback"],
  },
  // ── Skills ──────────────────────────────────────────────────────────────
  {
    name: "security-scan", kind: "Skill", icon: "shield",
    desc: "Static analysis plus dependency CVE scanning, distilled into a pass/fail checklist.",
    plat: "macOS · Linux", version: "3.0.2", rating: 4.5, installs: "15.9k",
    requires: ["semgrep", "trivy"], permissions: ["fs:read", "net:advisory-db"],
  },
  {
    name: "sql-explain", kind: "Skill", icon: "database",
    desc: "Explains query plans, flags missing indexes, and rewrites the hot paths.",
    plat: "all", version: "1.4.0", rating: 4.3, installs: "6.2k",
    requires: ["postgres"], permissions: ["db:read"],
  },
  {
    name: "doc-writer", kind: "Skill", icon: "file-text",
    desc: "Turns a diff or a module into reference docs with examples that actually run.",
    plat: "all", version: "2.1.5", rating: 4.6, installs: "9.8k",
    requires: ["Claude Code"], permissions: ["fs:read", "fs:write"],
  },
  {
    name: "test-author", kind: "Skill", icon: "check-check",
    desc: "Reads a function, generates table-driven tests, and runs them until green.",
    plat: "macOS · Linux", version: "1.7.2", rating: 4.4, installs: "5.5k",
    requires: ["Claude Code"], permissions: ["fs:write", "shell:exec"],
  },
  // ── Plugins ─────────────────────────────────────────────────────────────
  {
    name: "browser-use", kind: "Plugin", icon: "globe",
    desc: "Playwright browser automation pack — navigate, fill, screenshot, assert.",
    plat: "all", version: "0.12.0", rating: 4.7, installs: "18.6k",
    requires: ["chromium"], permissions: ["net:outbound", "fs:tmp"],
  },
  {
    name: "github", kind: "Plugin", icon: "git-branch",
    desc: "PRs, issues, and reviews as first-class tools — a one-line MCP quick-install.",
    plat: "all", version: "4.5.1", rating: 4.9, installs: "31.2k",
    requires: ["mcp"], permissions: ["repo:read", "repo:write"],
  },
  {
    name: "postgres", kind: "Plugin", icon: "database",
    desc: "Read-only SQL over a connection string, exposed as a scoped MCP server.",
    plat: "all", version: "2.0.3", rating: 4.4, installs: "11.0k",
    requires: ["mcp"], permissions: ["db:read"],
  },
  {
    name: "slack", kind: "Plugin", icon: "slack",
    desc: "Post, react, and open threads — the channel side of HITL and notifications.",
    plat: "all", version: "3.3.0", rating: 4.6, installs: "14.7k",
    requires: ["mcp"], permissions: ["chat:write", "channels:read"],
  },
];

const KIND_OPTIONS: { value: Kind; label: string }[] = [
  { value: "Agent", label: "Agents" },
  { value: "Skill", label: "Skills" },
  { value: "Plugin", label: "Plugins" },
];

export default function Marketplace() {
  const navigate = useNavigate();
  const setWizard = useUI((s) => s.setWizard);
  const showToast = useUI((s) => s.showToast);
  const { data: daemons = [] } = useDaemons();

  const [kind, setKind] = useState<Kind>("Agent");
  const [query, setQuery] = useState("");
  // The listing whose install flow is open (skills/plugins → daemon picker).
  const [installing, setInstalling] = useState<Listing | null>(null);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return CATALOG.filter(
      (m) => m.kind === kind && (!q || m.name.toLowerCase().includes(q) || m.desc.toLowerCase().includes(q)),
    );
  }, [kind, query]);

  function onInstall(m: Listing) {
    if (m.kind === "Agent") {
      // Agent templates seed a new agent — open the New Agent wizard.
      setWizard(true);
      navigate("/agents");
      return;
    }
    // Skills/plugins provision onto a target daemon — pick one first.
    setInstalling(m);
  }

  const onlineDaemons = daemons.filter((d) => d.status === "online");

  function provision(daemonName: string) {
    const m = installing;
    setInstalling(null);
    if (m) showToast({ text: `Provisioning ${m.name} on ${daemonName}` });
  }

  return (
    <>
      <PageHead
        kicker="Marketplace" title="Install in" serif="one click"
        sub="Agents, skills, and capability packs. Pick a target daemon and the item is provisioned onto it."
      />
      <div className="db-toolbar">
        <Segmented value={kind} onChange={setKind} options={KIND_OPTIONS} />
        <div className="db-toolbar-r">
          <div className="db-search-inline">
            <Icon name="search" size={15} style={{ color: "var(--mute)" }} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${kind.toLowerCase()}s…`}
              aria-label="Search the marketplace"
            />
          </div>
        </div>
      </div>

      <div className="db-market-grid">
        {items.map((m) => (
          <div key={m.name} className="db-market-card">
            <div className="db-market-top">
              <span className="db-market-icon"><Icon name={m.icon} size={18} /></span>
              <span className="db-market-kind db-mono">{m.kind}</span>
            </div>
            <div className="db-market-name">{m.name}</div>
            <p className="db-market-desc">{m.desc}</p>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
              {m.requires.map((r) => (
                <span key={r} className="db-tag" title="Required tool / MCP">{r}</span>
              ))}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
              {m.permissions.map((p) => (
                <span key={p} className="db-tag db-mono" title="Requested permission">
                  <Icon name="lock" size={10} style={{ marginRight: 4, verticalAlign: "-1px" }} />{p}
                </span>
              ))}
            </div>

            <div className="db-market-foot">
              <span className="db-mono db-muted">{m.plat}</span>
              <span className="db-market-rating db-mono"><Icon name="star" size={12} /> {m.rating}</span>
            </div>
            <div className="db-market-foot">
              <span className="db-mono db-muted">v{m.version}</span>
              <span className="db-mono db-muted">{m.installs} installs</span>
            </div>

            <Button variant="outline-light" icon="download" onClick={() => onInstall(m)}>Install</Button>
          </div>
        ))}
      </div>

      {items.length === 0 && (
        <div className="db-empty" style={{ marginTop: 8 }}>
          <span className="db-empty-icon"><Icon name="search" size={22} /></span>
          <div className="db-empty-caption">
            No {kind.toLowerCase()}s match <b style={{ color: "var(--ink)" }}>{query}</b>
          </div>
        </div>
      )}

      <Modal open={installing != null} onClose={() => setInstalling(null)} width={460}>
        <div className="db-dialog">
          <div className="db-dialog-icon"><Icon name="download" size={20} /></div>
          <h3 className="db-dialog-title">Install {installing?.name}</h3>
          <div className="db-dialog-body">
            Pick a target daemon — the {installing?.kind.toLowerCase()} is provisioned onto it
            with the requested permissions.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 18, textAlign: "left" }}>
            {onlineDaemons.length === 0 && (
              <div className="db-dialog-detail">No daemons are online right now.</div>
            )}
            {onlineDaemons.map((d) => (
              <button
                key={d.id}
                className="db-route-row db-mono"
                style={{ cursor: "pointer", justifyContent: "space-between", width: "100%" }}
                onClick={() => provision(d.name)}
              >
                <span>
                  <Icon name="server" size={13} style={{ verticalAlign: "-2px", marginRight: 8 }} />
                  {d.name}
                </span>
                <span className="db-muted">{d.platform}</span>
              </button>
            ))}
          </div>
          <div className="db-dialog-actions">
            <Button variant="outline-light" onClick={() => setInstalling(null)}>Cancel</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
