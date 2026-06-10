// Synapse Web UI — app shell: Sidebar + HeaderBar + CommandPalette + AppLayout.
// Ported from the prototype's Shell.jsx; navigation now runs on react-router.
import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Icon, LogoMark } from "./Primitives";
import { Toast } from "./Common";
import { useUI } from "../store/ui";
import { useOrg, useAgents, useDaemons, useAlerts } from "../api/queries";

interface NavItem { id: string; icon: string; name: string; path: string; badge?: "approvals" | "alerts" }
interface NavSection { label: string; items: NavItem[] }

const NAV_SECTIONS: NavSection[] = [
  { label: "Fleet", items: [
    { id: "dashboard", icon: "layout-dashboard", name: "Dashboard", path: "/" },
    { id: "agents", icon: "cpu", name: "Agents", path: "/agents" },
    { id: "daemons", icon: "server", name: "Daemons", path: "/daemons" },
  ] },
  { label: "Operate", items: [
    { id: "runs", icon: "activity", name: "Runs", path: "/runs" },
    { id: "approvals", icon: "shield", name: "Approvals", path: "/approvals", badge: "approvals" },
    { id: "alerts", icon: "bell-ring", name: "Alerts", path: "/alerts", badge: "alerts" },
  ] },
  { label: "Library", items: [
    { id: "marketplace", icon: "box", name: "Marketplace", path: "/marketplace" },
    { id: "webhooks", icon: "webhook", name: "Webhooks", path: "/webhooks" },
    { id: "notifications", icon: "mail", name: "Notifications", path: "/notifications" },
  ] },
];

const VIEW_TITLES: Record<string, string> = {
  "": "Dashboard", agents: "Agents", daemons: "Daemons", runs: "Runs",
  approvals: "Approvals", alerts: "Alerts", marketplace: "Marketplace",
  webhooks: "Webhooks", notifications: "Notifications", settings: "Settings",
  connect: "Connect a device", account: "Account",
};

function useCounts() {
  const approvals = useUI((s) => s.approvals.length);
  const { data: alerts } = useAlerts();
  return { approvals, alerts: alerts?.length ?? 0 };
}

function isActive(pathname: string, path: string): boolean {
  if (path === "/") return pathname === "/";
  return pathname === path || pathname.startsWith(path + "/");
}

function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const counts = useCounts();
  const { data: org } = useOrg();
  return (
    <aside className="db-sidebar">
      <div className="db-brand">
        <LogoMark size={24} />
        <span className="db-brand-word">Synapse</span>
      </div>
      <button className="db-connect-btn" onClick={() => navigate("/connect")}>
        <Icon name="plus" size={15} stroke={2} />
        <span>Connect a device</span>
      </button>
      <nav className="db-nav">
        {NAV_SECTIONS.map((sec) => (
          <div className="db-nav-sec" key={sec.label}>
            <div className="db-nav-label">{sec.label}</div>
            {sec.items.map((it) => {
              const c = it.badge ? counts[it.badge] : 0;
              return (
                <button
                  key={it.id}
                  className={"db-nav-item" + (isActive(location.pathname, it.path) ? " active" : "")}
                  onClick={() => navigate(it.path)}
                >
                  <Icon name={it.icon} size={16} />
                  <span>{it.name}</span>
                  {c > 0 && <span className="db-nav-badge">{c}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="db-side-foot">
        <button
          className={"db-nav-item" + (isActive(location.pathname, "/settings") ? " active" : "")}
          onClick={() => navigate("/settings")}
        >
          <Icon name="settings" size={16} /><span>Settings</span>
        </button>
        <button
          className={"db-nav-item" + (isActive(location.pathname, "/account/security") ? " active" : "")}
          onClick={() => navigate("/account/security")}
        >
          <Icon name="shield" size={16} /><span>Account security</span>
        </button>
        <button
          className={"db-nav-item" + (isActive(location.pathname, "/account/organizations") ? " active" : "")}
          onClick={() => navigate("/account/organizations")}
        >
          <Icon name="globe" size={16} /><span>Organizations</span>
        </button>
        <button className="db-ws-switch">
          <span className="db-ws-avatar">N</span>
          <span className="db-ws-meta">
            <span className="db-ws-name">{org?.name ?? ""}</span>
            <span className="db-ws-plan">{org?.plan ?? ""} workspace</span>
          </span>
          <Icon name="chevrons-up-down" size={14} style={{ color: "var(--mute)", marginLeft: "auto" }} />
        </button>
      </div>
    </aside>
  );
}

interface Crumb { label: string; to?: string }
function useCrumb(): Crumb[] {
  const { pathname } = useLocation();
  const { data: org } = useOrg();
  const { data: agents } = useAgents();
  const seg = pathname.split("/").filter(Boolean);
  const home: Crumb = { label: org?.name ?? "", to: "/" };
  if (seg.length === 0) return [home, { label: "Dashboard" }];
  if (seg[0] === "agents" && seg[1]) {
    const agent = (agents ?? []).find((a) => a.id === seg[1]);
    return [home, { label: "Agents", to: "/agents" }, { label: agent ? agent.name : "Agent" }];
  }
  return [home, { label: VIEW_TITLES[seg[0]] || seg[0] }];
}

function HeaderBar() {
  const navigate = useNavigate();
  const crumb = useCrumb();
  const counts = useCounts();
  const { data: org } = useOrg();
  const setPalette = useUI((s) => s.setPalette);
  const setTweaks = useUI((s) => s.setTweaks);
  return (
    <header className="db-header">
      <div className="db-crumb">
        {crumb.map((c, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            {i > 0 && <Icon name="chevron-right" size={13} style={{ color: "var(--mute)" }} />}
            {i === crumb.length - 1
              ? <span className="db-crumb-cur">{c.label}</span>
              : <button className="db-crumb-link" onClick={() => c.to && navigate(c.to)}>{c.label}</button>}
          </span>
        ))}
      </div>
      <div className="db-header-right">
        <button className="db-search" onClick={() => setPalette(true)}>
          <Icon name="search" size={15} style={{ color: "var(--mute)" }} />
          <span>Search agents, daemons, runs…</span>
          <span className="db-kbd">⌘K</span>
        </button>
        <button className="db-icon-btn" onClick={() => setTweaks(true)} title="Tweaks">
          <Icon name="sliders" size={17} />
        </button>
        <button className="db-icon-btn" onClick={() => navigate("/approvals")} title="Approvals">
          <Icon name="shield" size={17} />{counts.approvals > 0 && <span className="db-dot" />}
        </button>
        <button className="db-icon-btn" onClick={() => navigate("/alerts")} title="Alerts">
          <Icon name="bell" size={17} />{counts.alerts > 0 && <span className="db-dot" />}
        </button>
        <span className="db-avatar">{org?.initials ?? ""}</span>
      </div>
    </header>
  );
}

interface PaletteItem { icon: string; label: string; hint: string; go: string; wizard?: boolean }

function CommandPalette() {
  const navigate = useNavigate();
  const open = useUI((s) => s.paletteOpen);
  const setPalette = useUI((s) => s.setPalette);
  const setWizard = useUI((s) => s.setWizard);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const { data: agents } = useAgents();
  const { data: daemons } = useDaemons();

  const items = useMemo<PaletteItem[]>(() => {
    const base: PaletteItem[] = [
      { icon: "plus", label: "New agent", hint: "create", go: "/agents", wizard: true },
      { icon: "server", label: "Connect a device", hint: "pair", go: "/connect" },
      { icon: "shield", label: "Open approval queue", hint: "HITL", go: "/approvals" },
      { icon: "activity", label: "View all runs", hint: "runs", go: "/runs" },
      { icon: "cpu", label: "View agents", hint: "agents", go: "/agents" },
    ];
    const agentItems: PaletteItem[] = (agents ?? []).map((a) => ({ icon: "cpu", label: a.name, hint: a.engine, go: `/agents/${a.id}` }));
    const daemonItems: PaletteItem[] = (daemons ?? []).map((d) => ({ icon: "server", label: d.name, hint: d.os, go: "/daemons" }));
    const all = [...base, ...agentItems, ...daemonItems];
    if (!q.trim()) return all.slice(0, 8);
    return all.filter((i) => i.label.toLowerCase().includes(q.toLowerCase())).slice(0, 8);
  }, [q, agents, daemons]);

  function run(it: PaletteItem) {
    setPalette(false);
    if (it.wizard) setWizard(true);
    navigate(it.go);
  }

  useEffect(() => { setSel(0); }, [q]);
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPalette(false);
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
      if (e.key === "Enter" && items[sel]) { e.preventDefault(); run(items[sel]); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, items, sel]);

  if (!open) return null;
  return (
    <div className="db-palette-overlay" onClick={() => setPalette(false)}>
      <div className="db-palette" onClick={(e) => e.stopPropagation()}>
        <div className="db-palette-input">
          <span className="db-palette-prompt">›</span>
          <input autoFocus placeholder="Type a command or search…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="db-palette-list">
          {items.length === 0 && <div className="db-palette-empty">No matches</div>}
          {items.map((it, i) => (
            <div
              className={"db-palette-item" + (i === sel ? " sel" : "")} key={it.label + i}
              onMouseEnter={() => setSel(i)} onClick={() => run(it)}
            >
              <Icon name={it.icon} size={16} style={{ color: i === sel ? "var(--accent)" : "var(--mute)" }} />
              <span className="db-palette-label">{it.label}</span>
              <span className="db-palette-hint">{it.hint}</span>
            </div>
          ))}
        </div>
        <div className="db-palette-foot">
          <span className="db-kbd">↑</span><span className="db-kbd">↓</span> navigate
          <span className="db-kbd" style={{ marginLeft: 12 }}>↵</span> run
          <span className="db-kbd" style={{ marginLeft: 12 }}>esc</span> close
        </div>
      </div>
    </div>
  );
}

// Floating slot for the Tweaks panel (owned by screens/Tweaks.tsx). Mounted once so
// it is reachable from anywhere via the header control.
export function TweaksSlot({ children }: { children?: ReactNode }) {
  return <>{children}</>;
}

// Shown while a route's code-split chunk is fetched (usually a single frame).
function RouteFallback() {
  return (
    <div className="db-content" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span className="db-mono db-muted">Loading…</span>
    </div>
  );
}

export function AppLayout({ tweaks }: { tweaks?: ReactNode }) {
  const { pathname } = useLocation();
  const setPalette = useUI((s) => s.setPalette);
  const isConnect = pathname === "/connect";

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [setPalette]);

  return (
    <div className="db-app">
      <Sidebar />
      <div className="db-main">
        <HeaderBar />
        <Suspense fallback={<RouteFallback />}>
          {isConnect ? <Outlet /> : <div className="db-content fx-grid-light"><Outlet /></div>}
        </Suspense>
      </div>
      <CommandPalette />
      {tweaks}
      <Toast />
    </div>
  );
}
