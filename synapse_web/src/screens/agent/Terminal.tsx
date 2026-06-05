// Synapse Web UI — animated terminal chrome. Ported from
// design-reference/app/Terminal.jsx. Lines appear sequentially: command lines
// ~320ms apart, output ~140ms. Respects prefers-reduced-motion (shows all at
// once). Reusable wherever a terminal-style log readout is needed.
import { useEffect, useRef, useState } from "react";
import type { TraceLine } from "../../types";

export interface TerminalProps {
  /** Filename shown in the title bar. */
  file?: string;
  /** Lines to play out, in the terminal `TraceLine` shape. */
  lines: TraceLine[];
  /** Restart from the top after finishing. */
  loop?: boolean;
}

export function Terminal({ file = "night-cycle.log", lines, loop = true }: TerminalProps) {
  const [shown, setShown] = useState(0);
  const reduced = useRef(
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true,
  );

  useEffect(() => {
    if (reduced.current) {
      setShown(lines.length);
      return;
    }
    if (shown >= lines.length) {
      if (!loop) return;
      const t = window.setTimeout(() => setShown(0), 2600);
      return () => window.clearTimeout(t);
    }
    const isCmd = lines[shown].t === "cmd";
    const delay = shown === 0 ? 400 : isCmd ? 320 : 140;
    const t = window.setTimeout(() => setShown((s) => s + 1), delay);
    return () => window.clearTimeout(t);
  }, [shown, lines, loop]);

  return (
    <div className="terminal">
      <div className="term-bar">
        <span className="term-dots"><i /><i /><i /></span>
        <span className="term-file">{file}</span>
      </div>
      <div className="term-body" style={{ minHeight: 340 }}>
        {lines.slice(0, shown).map((l, i) => {
          if (l.t === "cmd")
            return (
              <div key={i}>
                <span className="term-prompt">$</span> {l.text}
                {l.comment && <span className="term-comment">  # {l.comment}</span>}
              </div>
            );
          return <div key={i} className={"term-out " + l.t}>{l.text}</div>;
        })}
        {shown >= lines.length && (
          <div><span className="term-prompt">$</span> <span className="term-cursor" /></div>
        )}
      </div>
    </div>
  );
}

export default Terminal;
