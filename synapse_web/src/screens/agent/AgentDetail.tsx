// Synapse Web UI — Agent Detail shell: hero row, enable toggle, run-now, and the
// tab nav + registry. The shell is foundation-owned and never edited by a worker;
// each tab's body lives in its own file under ./tabs and is filled in per unit.
import { Suspense, lazy, useState, type ComponentType, type LazyExoticComponent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Chip, Icon, Button } from "../../components/Primitives";
import { AgentAvatar, Toggle, daemonName } from "../../components/Common";
import { ScreenStub } from "../../components/Common";
import { useUI } from "../../store/ui";
import { data } from "../../api/queries";
import { AgentProvider } from "./context";

// Tabs are code-split: the heavy ones (Editor → CodeMirror, Analytics → Recharts,
// Runs → live trace) become async chunks fetched only when their tab is opened, so
// none of that weight is in the initial load. A Suspense boundary wraps the tab body.
const OverviewTab = lazy(() => import("./tabs/Overview"));
const EditorTab = lazy(() => import("./tabs/Editor"));
const VersionsTab = lazy(() => import("./tabs/Versions"));
const ScheduleTab = lazy(() => import("./tabs/Schedule"));
const ToolsTab = lazy(() => import("./tabs/Tools"));
const PluginsTab = lazy(() => import("./tabs/Plugins"));
const EnvironmentTab = lazy(() => import("./tabs/Environment"));
const MemoryTab = lazy(() => import("./tabs/Memory"));
const RunsTab = lazy(() => import("./tabs/Runs"));
const LogsTab = lazy(() => import("./tabs/Logs"));
const AnalyticsTab = lazy(() => import("./tabs/Analytics"));

interface TabDef { id: string; name: string; icon: string; Component: LazyExoticComponent<ComponentType> }

const AGENT_TABS: TabDef[] = [
  { id: "overview", name: "Overview", icon: "home", Component: OverviewTab },
  { id: "editor", name: "Editor", icon: "file-text", Component: EditorTab },
  { id: "versions", name: "Versions", icon: "history", Component: VersionsTab },
  { id: "schedule", name: "Schedule", icon: "calendar", Component: ScheduleTab },
  { id: "tools", name: "Tools & MCP", icon: "puzzle", Component: ToolsTab },
  { id: "plugins", name: "Plugins", icon: "plug", Component: PluginsTab },
  { id: "env", name: "Environment", icon: "key", Component: EnvironmentTab },
  { id: "memory", name: "Memory", icon: "brain", Component: MemoryTab },
  { id: "runs", name: "Runs", icon: "activity", Component: RunsTab },
  { id: "logs", name: "Logs", icon: "terminal", Component: LogsTab },
  { id: "analytics", name: "Analytics", icon: "gauge", Component: AnalyticsTab },
];

export default function AgentDetail() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const showToast = useUI((s) => s.showToast);

  const agent = data.agents.find((x) => x.id === agentId) ?? data.agents[0];
  const tab = params.get("tab") || "overview";
  const [enabled, setEnabled] = useState(agent.avail);

  function setTab(id: string) {
    setParams({ tab: id });
  }
  function runNow() {
    showToast({ text: `Run queued for ${agent.name}` });
    setTab("runs");
  }

  const Active = AGENT_TABS.find((t) => t.id === tab)?.Component;

  return (
    <AgentProvider agent={agent}>
      <div className="db-agentdetail">
        <div className="db-agent-hero">
          <button className="db-back" onClick={() => navigate("/agents")}>
            <Icon name="arrow-left" size={15} /> Agents
          </button>
          <div className="db-agent-hero-row">
            <div className="db-agent-hero-l">
              <AgentAvatar engine={agent.engine} size={52} />
              <div>
                <div className="db-agent-hero-name-row">
                  <h1 className="db-agent-hero-name">{agent.name}</h1>
                  <Chip s={enabled ? agent.status : "offline"} />
                </div>
                <div className="db-agent-hero-meta db-mono">
                  {agent.type} · {agent.engine} · <span className="db-accent">{agent.model}</span> · on{" "}
                  <button className="db-inline-link" onClick={() => navigate("/daemons")}>{daemonName(agent.daemonId)}</button>
                </div>
              </div>
            </div>
            <div className="db-agent-hero-actions">
              <div className="db-enable-wrap">
                <Toggle
                  on={enabled}
                  onChange={(v) => {
                    setEnabled(v);
                    showToast({ text: v ? `${agent.name} enabled` : `${agent.name} disabled`, variant: v ? "ok" : "warn" });
                  }}
                />
                <span className="db-enable-label db-mono">{enabled ? "enabled" : "disabled"}</span>
              </div>
              <Button variant="outline-light" icon="more-horizontal" onClick={() => showToast("Move / duplicate / delete")}>{" "}</Button>
              <Button variant="primary" icon="play" onClick={runNow} disabled={!enabled}>Run now</Button>
            </div>
          </div>
        </div>

        <div className="db-agent-tabs">
          {AGENT_TABS.map((t) => (
            <button key={t.id} className={"db-agent-tab" + (tab === t.id ? " active" : "")} onClick={() => setTab(t.id)}>
              <Icon name={t.icon} size={15} />{t.name}
            </button>
          ))}
        </div>

        <div className="db-agent-tabbody">
          <Suspense fallback={<div className="db-mono db-muted" style={{ padding: "24px 4px" }}>Loading…</div>}>
            {Active ? <Active /> : <ScreenStub name="Tab" />}
          </Suspense>
        </div>
      </div>
    </AgentProvider>
  );
}
