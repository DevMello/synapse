/* Synapse Web UI — shared view components */

function PageHead({ kicker, title, serif, sub, actions }) {
  return (
    <div className="db-pagehead">
      <div className="db-pagehead-l">
        {kicker && <Kicker>{kicker}</Kicker>}
        <h1 className="db-h1">{title} {serif && <span className="serif-accent">{serif}</span>}</h1>
        {sub && <p className="db-sub">{sub}</p>}
      </div>
      {actions && <div className="db-pagehead-actions">{actions}</div>}
    </div>
  );
}

function MetricCard({ label, n, unit, delta, dir, sub, onClick }) {
  return (
    <div className={'db-metric' + (onClick ? ' clickable' : '')} onClick={onClick}>
      <div className="db-metric-label">{label}</div>
      <div className="db-metric-n">{n}{unit && <span className="db-metric-unit"> {unit}</span>}</div>
      {delta && <div className={'db-metric-delta ' + (dir || '')}>{delta}</div>}
      {sub && <div className="db-metric-sub">{sub}</div>}
    </div>
  );
}

function SectionRow({ title, children }) {
  return (
    <div className="db-section-row">
      <h2 className="db-h2">{title}</h2>
      <div className="db-section-actions">{children}</div>
    </div>
  );
}

function Link({ icon, children, onClick }) {
  return (
    <button className="db-link" onClick={onClick}>
      {icon && <Icon name={icon} size={14} />}{children}
    </button>
  );
}

function Panel({ children, className, style }) {
  return <div className={'db-panel ' + (className || '')} style={style}>{children}</div>;
}

// Sparkline from an array of numbers
function Sparkline({ data, w = 120, h = 32, color = 'var(--accent)', fill = true }) {
  const max = Math.max(...data, 1), min = Math.min(...data, 0);
  const span = max - min || 1;
  const pts = data.map((v, i) => [ (i / (data.length - 1)) * w, h - ((v - min) / span) * (h - 4) - 2 ]);
  const d = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const area = d + ` L${w} ${h} L0 ${h} Z`;
  return (
    <svg width={w} height={h} style={{ display: 'block', overflow: 'visible' }}>
      {fill && <path d={area} fill={color} opacity="0.10" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Vertical bar chart
function BarChart({ data, h = 140, color = 'var(--accent)', labels }) {
  const max = Math.max(...data, 1);
  return (
    <div className="db-barchart" style={{ height: h }}>
      {data.map((v, i) => (
        <div key={i} className="db-bar-col">
          <div className="db-bar" style={{ height: (v / max) * (h - 22) + 'px', background: color }} title={String(v)} />
          {labels && <span className="db-bar-label">{labels[i]}</span>}
        </div>
      ))}
    </div>
  );
}

// Heartbeat / uptime strip
function HeartStrip({ data }) {
  return (
    <div className="db-heart">
      {data.map((v, i) => <span key={i} className={'db-heart-bar' + (v ? '' : ' down')} />)}
    </div>
  );
}

function EmptyState({ name, cmd, icon }) {
  return (
    <div className="db-empty">
      <HatchCorners onLight />
      {icon && <span className="db-empty-icon"><Icon name={icon} size={22} /></span>}
      <div className="db-empty-caption">
        No {name} yet{cmd && <> · run <span className="db-empty-cmd">{cmd}</span> to start</>}
      </div>
    </div>
  );
}

function AgentAvatar({ engine, size = 34 }) {
  const map = { 'Claude Code': 'terminal', 'Codex': 'code', 'Gemini CLI': 'sparkles', 'API': 'cpu' };
  return (
    <span className="db-agent-icon" style={{ width: size, height: size, borderRadius: size * 0.3 }}>
      <Icon name={map[engine] || 'cpu'} size={size * 0.46} />
    </span>
  );
}

function daemonName(id) { const d = DATA.daemons.find(x => x.id === id); return d ? d.name : id; }

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={'db-toast ' + (toast.kind || 'ok')}>
      <Icon name={toast.icon || 'check'} size={16} />
      <span>{toast.msg}</span>
    </div>
  );
}

// Toggle switch
function Toggle({ on, onChange, disabled }) {
  return (
    <button className={'db-toggle' + (on ? ' on' : '') + (disabled ? ' disabled' : '')}
      onClick={() => !disabled && onChange(!on)} disabled={disabled} role="switch" aria-checked={on}>
      <span className="db-toggle-knob" />
    </button>
  );
}

function Segmented({ options, value, onChange }) {
  return (
    <div className="db-segmented">
      {options.map(o => (
        <button key={o.value} className={'db-seg' + (value === o.value ? ' active' : '')} onClick={() => onChange(o.value)}>
          {o.icon && <Icon name={o.icon} size={14} />}{o.label}
        </button>
      ))}
    </div>
  );
}

// Generic centered modal
function Modal({ open, onClose, children, width = 560, dark = false }) {
  React.useEffect(() => {
    if (!open) return;
    const h = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="db-modal-overlay" onClick={onClose}>
      <div className={'db-modal' + (dark ? ' dark' : '')} style={{ width }} onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

function ConfirmDialog({ open, onClose, onConfirm, title, body, confirmLabel = 'Confirm', danger }) {
  return (
    <Modal open={open} onClose={onClose} width={460}>
      <div className="db-dialog">
        <div className={'db-dialog-icon' + (danger ? ' danger' : '')}>
          <Icon name={danger ? 'alert-triangle' : 'help-circle'} size={20} />
        </div>
        <h3 className="db-dialog-title">{title}</h3>
        <div className="db-dialog-body">{body}</div>
        <div className="db-dialog-actions">
          <Button variant="outline-light" onClick={onClose}>Cancel</Button>
          <button className={'btn ' + (danger ? 'btn-danger' : 'btn-primary')} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </Modal>
  );
}

Object.assign(window, { PageHead, MetricCard, SectionRow, Link, Panel, Sparkline, BarChart, HeartStrip, EmptyState, AgentAvatar, daemonName, Toast, Toggle, Segmented, Modal, ConfirmDialog });
