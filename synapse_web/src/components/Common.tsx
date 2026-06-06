// Synapse Web UI — shared view components, ported from the prototype's Common.jsx.
// Screens compose these with the bespoke `.db-*` classes from src/styles/app.css.
import { useEffect, type CSSProperties, type ReactNode } from "react";
import { Button, HatchCorners, Icon, Kicker } from "./Primitives";
import { useUI } from "../store/ui";
import { data } from "../api/queries";
import { queryClient } from "../lib/queryClient";
import type { Daemon } from "../types";

export function PageHead({
  kicker, title, serif, sub, actions,
}: {
  kicker?: ReactNode; title: ReactNode; serif?: ReactNode; sub?: ReactNode; actions?: ReactNode;
}) {
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

export function MetricCard({
  label, n, unit, delta, dir, sub, onClick,
}: {
  label: ReactNode; n: ReactNode; unit?: ReactNode; delta?: ReactNode;
  dir?: "up" | "down" | ""; sub?: ReactNode; onClick?: () => void;
}) {
  return (
    <div className={"db-metric" + (onClick ? " clickable" : "")} onClick={onClick}>
      <div className="db-metric-label">{label}</div>
      <div className="db-metric-n">{n}{unit && <span className="db-metric-unit"> {unit}</span>}</div>
      {delta && <div className={"db-metric-delta " + (dir || "")}>{delta}</div>}
      {sub && <div className="db-metric-sub">{sub}</div>}
    </div>
  );
}

export function SectionRow({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="db-section-row">
      <h2 className="db-h2">{title}</h2>
      <div className="db-section-actions">{children}</div>
    </div>
  );
}

export function Link({ icon, children, onClick }: { icon?: string; children?: ReactNode; onClick?: () => void }) {
  return (
    <button className="db-link" onClick={onClick}>
      {icon && <Icon name={icon} size={14} />}{children}
    </button>
  );
}

export function Panel({ children, className, style }: { children?: ReactNode; className?: string; style?: CSSProperties }) {
  return <div className={"db-panel " + (className || "")} style={style}>{children}</div>;
}

// Sparkline from an array of numbers.
export function Sparkline({
  data: series, w = 120, h = 32, color = "var(--accent)", fill = true,
}: {
  data: number[]; w?: number; h?: number; color?: string; fill?: boolean;
}) {
  const max = Math.max(...series, 1), min = Math.min(...series, 0);
  const span = max - min || 1;
  const pts = series.map((v, i) => [(i / (series.length - 1)) * w, h - ((v - min) / span) * (h - 4) - 2]);
  const d = pts.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = d + ` L${w} ${h} L0 ${h} Z`;
  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      {fill && <path d={area} fill={color} opacity="0.10" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Vertical bar chart.
export function BarChart({
  data: series, h = 140, color = "var(--accent)", labels,
}: {
  data: number[]; h?: number; color?: string; labels?: string[];
}) {
  const max = Math.max(...series, 1);
  return (
    <div className="db-barchart" style={{ height: h }}>
      {series.map((v, i) => (
        <div key={i} className="db-bar-col">
          <div className="db-bar" style={{ height: (v / max) * (h - 22) + "px", background: color }} title={String(v)} />
          {labels && <span className="db-bar-label">{labels[i]}</span>}
        </div>
      ))}
    </div>
  );
}

// Heartbeat / uptime strip.
export function HeartStrip({ data: series }: { data: number[] }) {
  return (
    <div className="db-heart">
      {series.map((v, i) => <span key={i} className={"db-heart-bar" + (v ? "" : " down")} />)}
    </div>
  );
}

export function EmptyState({ name, cmd, icon }: { name: ReactNode; cmd?: string; icon?: string }) {
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

const ENGINE_ICON: Record<string, string> = {
  "Claude Code": "terminal", Codex: "code", "Gemini CLI": "sparkles", API: "cpu",
};

export function AgentAvatar({ engine, size = 34 }: { engine: string; size?: number }) {
  return (
    <span className="db-agent-icon" style={{ width: size, height: size, borderRadius: size * 0.3 }}>
      <Icon name={ENGINE_ICON[engine] || "cpu"} size={size * 0.46} />
    </span>
  );
}

export function daemonName(id: string): string {
  // Read the live daemons from the query cache; fall back to the mock snapshot
  // until the ["daemons"] query has populated.
  const daemons = queryClient.getQueryData<Daemon[]>(["daemons"]) ?? data.daemons;
  const d = daemons.find((x) => x.id === id);
  return d ? d.name : id;
}

// Global toast bound to the UI store. Mount once in the app layout.
export function Toast() {
  const toast = useUI((s) => s.toast);
  if (!toast) return null;
  return (
    <div className={"db-toast " + (toast.variant || "ok")}>
      <Icon name={toast.variant === "warn" ? "alert-triangle" : "check"} size={16} />
      <span>{toast.text}</span>
    </div>
  );
}

export function Toggle({ on, onChange, disabled }: { on: boolean; onChange: (next: boolean) => void; disabled?: boolean }) {
  return (
    <button
      className={"db-toggle" + (on ? " on" : "") + (disabled ? " disabled" : "")}
      onClick={() => !disabled && onChange(!on)} disabled={disabled} role="switch" aria-checked={on}
    >
      <span className="db-toggle-knob" />
    </button>
  );
}

export interface SegOption<T extends string = string> { value: T; label: ReactNode; icon?: string }
export function Segmented<T extends string = string>({
  options, value, onChange,
}: {
  options: SegOption<T>[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="db-segmented">
      {options.map((o) => (
        <button key={o.value} className={"db-seg" + (value === o.value ? " active" : "")} onClick={() => onChange(o.value)}>
          {o.icon && <Icon name={o.icon} size={14} />}{o.label}
        </button>
      ))}
    </div>
  );
}

// Generic centered modal.
export function Modal({
  open, onClose, children, width = 560, dark = false,
}: {
  open: boolean; onClose: () => void; children?: ReactNode; width?: number; dark?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="db-modal-overlay" onClick={onClose}>
      <div className={"db-modal" + (dark ? " dark" : "")} style={{ width }} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open, onClose, onConfirm, title, body, confirmLabel = "Confirm", danger,
}: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: ReactNode;
  body: ReactNode; confirmLabel?: string; danger?: boolean;
}) {
  return (
    <Modal open={open} onClose={onClose} width={460}>
      <div className="db-dialog">
        <div className={"db-dialog-icon" + (danger ? " danger" : "")}>
          <Icon name={danger ? "alert-triangle" : "help-circle"} size={20} />
        </div>
        <h3 className="db-dialog-title">{title}</h3>
        <div className="db-dialog-body">{body}</div>
        <div className="db-dialog-actions">
          <Button variant="outline-light" onClick={onClose}>Cancel</Button>
          <button className={"btn " + (danger ? "btn-danger" : "btn-primary")} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </Modal>
  );
}

// Placeholder for screens/tabs not yet implemented — keeps the build green and the
// shell navigable while a worker fills in the real screen. On-brand, never blank.
export function ScreenStub({ name, note }: { name: string; note?: string }) {
  return (
    <div className="db-empty" style={{ marginTop: 8 }}>
      <HatchCorners onLight />
      <span className="db-empty-icon"><Icon name="sparkles" size={22} /></span>
      <div className="db-empty-caption">
        <b style={{ color: "var(--ink)" }}>{name}</b> — coming together
        {note && <> · {note}</>}
      </div>
    </div>
  );
}
