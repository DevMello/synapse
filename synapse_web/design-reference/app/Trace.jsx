/* Synapse Web UI — Live trace viewer (streaming reasoning + cost) */

const TRACE_EVENTS = [
  { type: 'meta', text: 'run #2214 · trigger: webhook (PR #2214 opened) · host my-macbook-pro', tok: 0, cost: 0 },
  { type: 'prompt', label: 'system', text: 'Review the diff against the northwind ruleset. Gate coverage at 80%.', tok: 1200, cost: 0.004 },
  { type: 'think', text: 'Plan: read the diff, run coverage, scan for off-list network calls, write the report.', tok: 540, cost: 0.006 },
  { type: 'tool-call', tool: 'git.diff', args: 'PR #2214', text: 'Resolving changed files…', tok: 80, cost: 0.0 },
  { type: 'tool-result', tool: 'git.diff', text: '14 files changed (+612 / −188) across 3 modules.', tok: 3100, cost: 0.012 },
  { type: 'think', text: 'payments/retries.ts adds a new outbound call. Need to check it against the allow-list.', tok: 620, cost: 0.007 },
  { type: 'tool-call', tool: 'shell.coverage', args: 'vitest --coverage', text: 'Running test suite…', tok: 60, cost: 0.0 },
  { type: 'tool-result', tool: 'shell.coverage', text: 'coverage 78.4% — 1.6 pts under the 80% gate.', tok: 2400, cost: 0.009, level: 'warn' },
  { type: 'tool-call', tool: 'fetch', args: 'api.unknown-vendor.com', text: 'Probing new network call…', tok: 40, cost: 0.0 },
  { type: 'guard', cat: 'tool-bypass', text: 'fetch to api.unknown-vendor.com blocked — host not on the network allow-list.', action: 'blocked', tok: 0, cost: 0 },
  { type: 'think', text: 'Coverage gate failed and a new off-list call appeared. I will request changes, not approve.', tok: 700, cost: 0.008 },
  { type: 'tool-call', tool: 'fs.write', args: 'reports/review/2214.md', text: 'Writing review report…', tok: 120, cost: 0.0 },
  { type: 'redact', text: 'masked 1 secret (<REDACTED:API_KEY>) before upload', tok: 0, cost: 0 },
  { type: 'completion', text: 'Requested changes on PR #2214: restore coverage to ≥80% and remove the api.unknown-vendor.com call (or add it to the allow-list with a reason).', tok: 1800, cost: 0.021 },
  { type: 'done', text: 'run complete · exit gate · 1m 12s', tok: 0, cost: 0 },
];

function TraceViewer({ autoplay = true, height, embedded }) {
  const [shown, setShown] = React.useState(autoplay ? 1 : TRACE_EVENTS.length);
  const [playing, setPlaying] = React.useState(autoplay);
  const bodyRef = React.useRef(null);

  React.useEffect(() => {
    if (!playing || shown >= TRACE_EVENTS.length) return;
    const ev = TRACE_EVENTS[shown];
    const delay = ev.type === 'tool-result' || ev.type === 'completion' ? 1100 : ev.type === 'think' ? 850 : 650;
    const t = setTimeout(() => setShown(s => s + 1), delay);
    return () => clearTimeout(t);
  }, [shown, playing]);

  React.useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [shown]);

  const visible = TRACE_EVENTS.slice(0, shown);
  const tokens = visible.reduce((s, e) => s + (e.tok || 0), 0);
  const cost = visible.reduce((s, e) => s + (e.cost || 0), 0);
  const live = shown < TRACE_EVENTS.length;
  const done = TRACE_EVENTS[shown - 1] && TRACE_EVENTS[shown - 1].type === 'done';

  return (
    <div className={'db-trace' + (embedded ? ' embedded' : '')}>
      <div className="db-trace-head">
        <div className="db-trace-head-l">
          {live ? <span className="status-chip running">streaming</span>
            : done ? <span className="status-chip blocked">gated</span>
            : <span className="status-chip passed">replay</span>}
          <span className="db-trace-title db-mono">pr-reviewer · run #2214</span>
        </div>
        <div className="db-trace-stats">
          <div className="db-trace-stat"><span className="db-trace-stat-n db-mono">{tokens.toLocaleString()}</span><span className="db-trace-stat-l">tokens</span></div>
          <div className="db-trace-stat"><span className="db-trace-stat-n db-mono">${cost.toFixed(3)}</span><span className="db-trace-stat-l">cost</span></div>
          <button className="db-trace-ctl" onClick={() => { if (!live) { setShown(1); setPlaying(true); } else setPlaying(p => !p); }}>
            <Icon name={!live ? 'rotate-ccw' : playing ? 'pause' : 'play'} size={14} stroke={2} />
            {!live ? 'Replay' : playing ? 'Pause' : 'Play'}
          </button>
        </div>
      </div>

      <div className="db-trace-body" ref={bodyRef} style={height ? { maxHeight: height } : null}>
        {visible.map((e, i) => <TraceEvent key={i} e={e} />)}
        {live && <div className="db-trace-cursor"><span className="term-cursor" /></div>}
      </div>
    </div>
  );
}

function TraceEvent({ e }) {
  if (e.type === 'meta')
    return <div className="db-tev meta db-mono"><Icon name="git-commit" size={13} /> {e.text}</div>;
  if (e.type === 'prompt')
    return <div className="db-tev prompt"><span className="db-tev-tag prompt">{e.label}</span><span className="db-tev-text">{e.text}</span></div>;
  if (e.type === 'think')
    return <div className="db-tev think"><Icon name="brain" size={14} className="db-tev-glyph" /><span className="db-tev-text">{e.text}</span></div>;
  if (e.type === 'tool-call')
    return <div className="db-tev toolcall"><span className="db-tev-tag tool db-mono">{e.tool}</span><span className="db-tev-args db-mono">{e.args}</span><span className="db-tev-text">{e.text}</span></div>;
  if (e.type === 'tool-result')
    return <div className={'db-tev toolresult' + (e.level === 'warn' ? ' warn' : '')}><span className="db-tev-rail" /><span className="db-tev-text db-mono">{e.text}</span></div>;
  if (e.type === 'guard')
    return <div className="db-tev guard"><span className="db-tev-tag guard"><Icon name="shield-alert" size={12} /> {e.cat}</span><span className="db-tev-text">{e.text}</span><span className="db-tev-action">{e.action}</span></div>;
  if (e.type === 'redact')
    return <div className="db-tev redact db-mono"><Icon name="lock" size={13} /> {e.text}</div>;
  if (e.type === 'completion')
    return <div className="db-tev completion"><span className="db-tev-tag done">output</span><span className="db-tev-text">{e.text}</span></div>;
  if (e.type === 'done')
    return <div className="db-tev donerow db-mono"><Icon name="check-circle" size={14} /> {e.text}</div>;
  return null;
}

Object.assign(window, { TraceViewer, TRACE_EVENTS });
