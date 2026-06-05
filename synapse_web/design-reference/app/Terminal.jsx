/* Synapse UI Kit — animated Terminal (landing)
   Lines appear sequentially: command lines ~320ms apart, output ~140ms. */

function Terminal({ file = 'night-cycle.log', lines, loop = true }) {
  const [shown, setShown] = React.useState(0);
  const reduced = React.useRef(window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  React.useEffect(() => {
    if (reduced.current) { setShown(lines.length); return; }
    if (shown >= lines.length) {
      if (!loop) return;
      const t = setTimeout(() => setShown(0), 2600);
      return () => clearTimeout(t);
    }
    const isCmd = lines[shown].t === 'cmd';
    const delay = shown === 0 ? 400 : (isCmd ? 320 : 140);
    const t = setTimeout(() => setShown(s => s + 1), delay);
    return () => clearTimeout(t);
  }, [shown, lines, loop]);

  return (
    <div className="terminal">
      <div className="term-bar">
        <span className="term-dots"><i /><i /><i /></span>
        <span className="term-file">{file}</span>
      </div>
      <div className="term-body" style={{ minHeight: 340 }}>
        {lines.slice(0, shown).map((l, i) => {
          if (l.t === 'cmd')
            return <div key={i}><span className="term-prompt">$</span> {l.text}{l.comment && <span className="term-comment">  # {l.comment}</span>}</div>;
          if (l.t === 'comment')
            return <div key={i} className="term-comment">{l.text}</div>;
          return <div key={i} className={'term-out ' + (l.t)}>{l.text}</div>;
        })}
        {shown >= lines.length && <div><span className="term-prompt">$</span> <span className="term-cursor" /></div>}
      </div>
    </div>
  );
}

const NIGHT_LINES = [
  { t: 'cmd', text: 'agency night sword-game', comment: '11:00 PM — 05:00 AM EST' },
  { t: 'info', text: 'plan: decomposed into 6 tasks, gates armed' },
  { t: 'info', text: 'host: macbook-pro-m3 · keys stay local' },
  { t: 'ok', text: 'build: feat(sword-game) add dash mechanic → PR #214' },
  { t: 'ok', text: 'qa: 12 specs green · coverage 84%' },
  { t: 'warn', text: 'plan: replanned 3 tasks after blocked write' },
  { t: 'ok', text: 'mcp: redacted 2 secrets before commit' },
  { t: 'info', text: 'wrote reports/morning/2026-06-03.md' },
];

Object.assign(window, { Terminal, NIGHT_LINES });
