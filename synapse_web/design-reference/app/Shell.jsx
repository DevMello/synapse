/* Synapse Web UI — Shell: Sidebar + HeaderBar + CommandPalette */

const NAV_SECTIONS = [
  { label: 'Fleet', items: [
    { id: 'dashboard', icon: 'layout-dashboard', name: 'Dashboard' },
    { id: 'agents', icon: 'cpu', name: 'Agents' },
    { id: 'daemons', icon: 'server', name: 'Daemons' },
  ]},
  { label: 'Operate', items: [
    { id: 'runs', icon: 'activity', name: 'Runs' },
    { id: 'approvals', icon: 'shield', name: 'Approvals', badge: 'approvals' },
    { id: 'alerts', icon: 'bell-ring', name: 'Alerts', badge: 'alerts' },
  ]},
  { label: 'Library', items: [
    { id: 'marketplace', icon: 'box', name: 'Marketplace' },
    { id: 'webhooks', icon: 'webhook', name: 'Webhooks' },
    { id: 'notifications', icon: 'mail', name: 'Notifications' },
  ]},
];

function Sidebar({ route, nav, counts }) {
  const active = route.view;
  return (
    <aside className="db-sidebar">
      <div className="db-brand">
        <LogoMark size={24} />
        <span className="db-brand-word">Synapse</span>
      </div>
      <button className="db-connect-btn" onClick={() => nav({ view: 'connect' })}>
        <Icon name="plus" size={15} stroke={2} />
        <span>Connect a device</span>
      </button>
      <nav className="db-nav">
        {NAV_SECTIONS.map(sec => (
          <div className="db-nav-sec" key={sec.label}>
            <div className="db-nav-label">{sec.label}</div>
            {sec.items.map(it => {
              const c = it.badge ? counts[it.badge] : 0;
              return (
                <button key={it.id} className={'db-nav-item' + (active === it.id ? ' active' : '')} onClick={() => nav({ view: it.id })}>
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
        <button className={'db-nav-item' + (active === 'settings' ? ' active' : '')} onClick={() => nav({ view: 'settings' })}>
          <Icon name="settings" size={16} /><span>Settings</span>
        </button>
        <button className="db-ws-switch">
          <span className="db-ws-avatar">N</span>
          <span className="db-ws-meta">
            <span className="db-ws-name">{DATA.ORG.name}</span>
            <span className="db-ws-plan">{DATA.ORG.plan} workspace</span>
          </span>
          <Icon name="chevrons-up-down" size={14} style={{ color: 'var(--mute)', marginLeft: 'auto' }} />
        </button>
      </div>
    </aside>
  );
}

function HeaderBar({ crumb, nav, onPalette, counts }) {
  return (
    <header className="db-header">
      <div className="db-crumb">
        {crumb.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && <Icon name="chevron-right" size={13} style={{ color: 'var(--mute)' }} />}
            {i === crumb.length - 1
              ? <span className="db-crumb-cur">{c.label}</span>
              : <button className="db-crumb-link" onClick={() => c.to && nav(c.to)}>{c.label}</button>}
          </React.Fragment>
        ))}
      </div>
      <div className="db-header-right">
        <button className="db-search" onClick={onPalette}>
          <Icon name="search" size={15} style={{ color: 'var(--mute)' }} />
          <span>Search agents, daemons, runs…</span>
          <span className="db-kbd">⌘K</span>
        </button>
        <button className="db-icon-btn" onClick={() => nav({ view: 'approvals' })} title="Approvals">
          <Icon name="shield" size={17} />{counts.approvals > 0 && <span className="db-dot" />}
        </button>
        <button className="db-icon-btn" onClick={() => nav({ view: 'alerts' })} title="Alerts">
          <Icon name="bell" size={17} />{counts.alerts > 0 && <span className="db-dot" />}
        </button>
        <span className="db-avatar">{DATA.ORG.initials}</span>
      </div>
    </header>
  );
}

function CommandPalette({ open, onClose, nav }) {
  const [q, setQ] = React.useState('');
  const [sel, setSel] = React.useState(0);

  const items = React.useMemo(() => {
    const base = [
      { icon: 'plus', label: 'New agent', hint: 'create', go: { view: 'agents', newAgent: true } },
      { icon: 'server', label: 'Connect a device', hint: 'pair', go: { view: 'connect' } },
      { icon: 'shield', label: 'Open approval queue', hint: 'HITL', go: { view: 'approvals' } },
      { icon: 'activity', label: 'View all runs', hint: 'runs', go: { view: 'runs' } },
      { icon: 'cpu', label: 'View agents', hint: 'agents', go: { view: 'agents' } },
    ];
    const agentItems = DATA.agents.map(a => ({ icon: 'cpu', label: a.name, hint: a.engine, go: { view: 'agent', agentId: a.id } }));
    const daemonItems = DATA.daemons.map(d => ({ icon: 'server', label: d.name, hint: d.os, go: { view: 'daemons' } }));
    const all = [...base, ...agentItems, ...daemonItems];
    if (!q.trim()) return all.slice(0, 8);
    return all.filter(i => i.label.toLowerCase().includes(q.toLowerCase())).slice(0, 8);
  }, [q]);

  React.useEffect(() => { setSel(0); }, [q]);
  React.useEffect(() => {
    const h = e => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, items.length - 1)); }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); }
      if (e.key === 'Enter' && items[sel]) { onClose(); nav(items[sel].go); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose, items, sel, nav]);

  if (!open) return null;
  return (
    <div className="db-palette-overlay" onClick={onClose}>
      <div className="db-palette" onClick={e => e.stopPropagation()}>
        <div className="db-palette-input">
          <span className="db-palette-prompt">›</span>
          <input autoFocus placeholder="Type a command or search…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <div className="db-palette-list">
          {items.length === 0 && <div className="db-palette-empty">No matches</div>}
          {items.map((it, i) => (
            <div className={'db-palette-item' + (i === sel ? ' sel' : '')} key={it.label + i}
              onMouseEnter={() => setSel(i)} onClick={() => { onClose(); nav(it.go); }}>
              <Icon name={it.icon} size={16} style={{ color: i === sel ? 'var(--accent)' : 'var(--mute)' }} />
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

Object.assign(window, { Sidebar, HeaderBar, CommandPalette });
