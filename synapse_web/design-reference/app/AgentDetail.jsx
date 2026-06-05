/* Synapse Web UI — Agent Detail: header + tab nav + Overview */

const AGENT_TABS = [
  { id: 'overview', name: 'Overview', icon: 'home' },
  { id: 'editor', name: 'Editor', icon: 'file-text' },
  { id: 'versions', name: 'Versions', icon: 'history' },
  { id: 'schedule', name: 'Schedule', icon: 'calendar' },
  { id: 'tools', name: 'Tools & MCP', icon: 'puzzle' },
  { id: 'env', name: 'Environment', icon: 'key' },
  { id: 'memory', name: 'Memory', icon: 'brain' },
  { id: 'runs', name: 'Runs', icon: 'activity' },
  { id: 'logs', name: 'Logs', icon: 'terminal' },
  { id: 'analytics', name: 'Analytics', icon: 'gauge' },
];

function AgentDetail({ route, nav, toast }) {
  const a = DATA.agents.find(x => x.id === route.agentId) || DATA.agents[0];
  const tab = route.tab || 'overview';
  const d = DATA.daemons.find(x => x.id === a.daemonId);
  const [enabled, setEnabled] = React.useState(a.avail);

  function runNow() { toast({ msg: `Run queued for ${a.name}`, icon: 'play' }); nav({ view: 'agent', agentId: a.id, tab: 'runs' }); }

  let body;
  if (tab === 'overview') body = <AgentOverview a={a} d={d} nav={nav} />;
  else if (tab === 'editor') body = <EditorTab a={a} toast={toast} />;
  else if (tab === 'versions') body = <VersionsTab a={a} toast={toast} />;
  else if (tab === 'schedule') body = <ScheduleTab a={a} toast={toast} />;
  else if (tab === 'tools') body = <ToolsTab a={a} d={d} nav={nav} toast={toast} />;
  else if (tab === 'env') body = <EnvTab a={a} d={d} toast={toast} />;
  else if (tab === 'memory') body = <MemoryTab a={a} toast={toast} />;
  else if (tab === 'runs') body = <RunsTab a={a} nav={nav} />;
  else if (tab === 'logs') body = <LogsTab a={a} />;
  else if (tab === 'analytics') body = <AnalyticsTab a={a} />;

  return (
    <div className="db-agentdetail">
      <div className="db-agent-hero">
        <button className="db-back" onClick={() => nav({ view: 'agents' })}><Icon name="arrow-left" size={15} /> Agents</button>
        <div className="db-agent-hero-row">
          <div className="db-agent-hero-l">
            <AgentAvatar engine={a.engine} size={52} />
            <div>
              <div className="db-agent-hero-name-row">
                <h1 className="db-agent-hero-name">{a.name}</h1>
                <Chip s={enabled ? a.status : 'offline'} />
              </div>
              <div className="db-agent-hero-meta db-mono">
                {a.type} · {a.engine} · <span className="db-accent">{a.model}</span> · on <button className="db-inline-link" onClick={() => nav({ view: 'daemons' })}>{daemonName(a.daemonId)}</button>
              </div>
            </div>
          </div>
          <div className="db-agent-hero-actions">
            <div className="db-enable-wrap">
              <Toggle on={enabled} onChange={v => { setEnabled(v); toast({ msg: v ? `${a.name} enabled` : `${a.name} disabled`, icon: v ? 'check' : 'pause', kind: v ? 'ok' : 'warn' }); }} />
              <span className="db-enable-label db-mono">{enabled ? 'enabled' : 'disabled'}</span>
            </div>
            <Button variant="outline-light" icon="more-horizontal" onClick={() => toast({ msg: 'Move / duplicate / delete', icon: 'more-horizontal' })}> </Button>
            <Button variant="primary" icon="play" onClick={runNow} disabled={!enabled}>Run now</Button>
          </div>
        </div>
      </div>

      <div className="db-agent-tabs">
        {AGENT_TABS.map(t => (
          <button key={t.id} className={'db-agent-tab' + (tab === t.id ? ' active' : '')} onClick={() => nav({ view: 'agent', agentId: a.id, tab: t.id })}>
            <Icon name={t.icon} size={15} />{t.name}
          </button>
        ))}
      </div>

      <div className="db-agent-tabbody">{body}</div>
    </div>
  );
}

function AgentOverview({ a, d, nav }) {
  const recent = DATA.runs.filter(r => r.agentId === a.id);
  return (
    <>
      <div className="db-ov-grid">
        <div className="db-ov-main">
          <div className="db-metric-grid db-metric-grid-3">
            <MetricCard label="Availability" n={a.avail ? 'Online' : 'Offline'} sub={a.avail ? `${daemonName(a.daemonId)} healthy` : 'host offline'} />
            <MetricCard label="Next run" n={a.nextRun} sub="timezone EST" />
            <MetricCard label="Spend today" n={'$' + a.spendToday.toFixed(2)} delta={`${(a.tokensToday/1e6).toFixed(2)}M tokens`} />
          </div>

          <SectionRow title="Recent runs">
            <Link icon="external-link" onClick={() => nav({ view: 'agent', agentId: a.id, tab: 'runs' })}>All runs</Link>
          </SectionRow>
          <div className="db-table-wrap">
            <table className="db-table">
              <thead><tr><th>Run</th><th>Trigger</th><th>Started</th><th>Duration</th><th>Cost</th><th>Status</th></tr></thead>
              <tbody>
                {recent.length ? recent.map(r => (
                  <tr key={r.id} className="clickable-row" onClick={() => nav({ view: 'agent', agentId: a.id, tab: 'runs', runId: r.id })}>
                    <td className="db-cell-primary db-mono">#{r.id.replace('r','')}</td>
                    <td className="db-mono">{r.trigger}</td>
                    <td className="db-mono">{r.started}</td>
                    <td className="db-mono">{r.dur}</td>
                    <td className="db-mono">${r.cost.toFixed(2)}</td>
                    <td><Chip s={r.status} /></td>
                  </tr>
                )) : <tr><td colSpan="6"><div className="db-muted db-mono" style={{ padding: '8px 0' }}>No runs yet.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className="db-ov-side">
          <div className="db-panel">
            <div className="db-panel-head"><h3 className="db-panel-title">Host</h3></div>
            <button className="db-ov-host" onClick={() => nav({ view: 'daemons' })}>
              <span className={'db-status-dot ' + (d ? d.status : 'offline')} />
              <div>
                <div className="db-ov-host-name">{d ? d.name : '—'}</div>
                <div className="db-ov-host-os db-mono">{d ? d.os : ''}</div>
              </div>
              <Icon name="chevron-right" size={16} style={{ color: 'var(--mute)', marginLeft: 'auto' }} />
            </button>
            <div className="db-ov-facts">
              <div className="db-ov-fact"><span className="db-ov-fact-l">Version</span><span className="db-mono">{a.model}</span></div>
              <div className="db-ov-fact"><span className="db-ov-fact-l">Error rate</span><span className="db-mono">{a.errRate}%</span></div>
              <div className="db-ov-fact"><span className="db-ov-fact-l">Total runs</span><span className="db-mono">{a.runsTotal.toLocaleString()}</span></div>
            </div>
          </div>

          <div className="db-panel">
            <div className="db-panel-head"><h3 className="db-panel-title">Quick edit</h3></div>
            <div className="db-ov-links">
              <button className="db-ov-link" onClick={() => nav({ view: 'agent', agentId: a.id, tab: 'editor' })}><Icon name="file-text" size={15} /> Prompt & skills <Icon name="chevron-right" size={15} className="db-ov-link-arr" /></button>
              <button className="db-ov-link" onClick={() => nav({ view: 'agent', agentId: a.id, tab: 'tools' })}><Icon name="puzzle" size={15} /> Tools & blockers <Icon name="chevron-right" size={15} className="db-ov-link-arr" /></button>
              <button className="db-ov-link" onClick={() => nav({ view: 'agent', agentId: a.id, tab: 'schedule' })}><Icon name="calendar" size={15} /> Schedule <Icon name="chevron-right" size={15} className="db-ov-link-arr" /></button>
              <button className="db-ov-link" onClick={() => nav({ view: 'agent', agentId: a.id, tab: 'memory' })}><Icon name="brain" size={15} /> Memory <Icon name="chevron-right" size={15} className="db-ov-link-arr" /></button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { AgentDetail });
