// Synapse Web UI — Tweaks panel (plan unit 22).
// A floating glass control panel (ported pixel-faithfully from the prototype's
// tweaks-panel.jsx) with THREE expressive controls that reshape the whole
// console's feel, not single-property pixel-pushing:
//
//   1. Density   — calm dashboard → mission-control. Scales the spacing scale,
//                  panel padding, card gap and content padding across the app.
//   2. Accent    — shifts the warmth (hue) of the single hero ember accent.
//   3. Liveness  — how alive the surface feels: scales motion durations and the
//                  trace/aurora/pulse animation speed, and can go fully still.
//
// Each control writes CSS custom properties on document.documentElement so the
// change ripples live across every screen (the whole .db-* / fx-* system reads
// these tokens). A small injected <style> (owned by this file) wires the few
// hardcoded paddings/animations in the design system to the same tokens so
// Density and Liveness reach surfaces that don't already consume a variable.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon } from "../components/Primitives";
import { useUI } from "../store/ui";

// ── Defaults (mid-points) ────────────────────────────────────────────────────
const DENSITY_DEFAULT = 1; // 0 = calm/airy, 1 = balanced, 2 = mission-control
const ACCENT_DEFAULT = 18; // hue of the ember accent (deg). 18° ≈ stock #ef6a2a.
const LIVENESS_DEFAULT = 65; // 0 = still, 100 = vivid

const DENSITY_OPTS = ["Calm", "Balanced", "Mission"] as const;
type DensityLevel = 0 | 1 | 2;

// Density scales the whole spacing system by a single factor; padding/gap follow.
const DENSITY_SCALE: Record<DensityLevel, number> = { 0: 1.16, 1: 1, 2: 0.74 };

// ── Color helpers (HSL ember → hex/rgb). s and l are percentages (0–100). ─────
function hslChannels(h: number, s: number, l: number): [number, number, number] {
  const sn = s / 100;
  const ln = l / 100;
  const a = sn * Math.min(ln, 1 - ln);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    return Math.round(255 * (ln - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
  };
  return [f(0), f(8), f(4)];
}

function hslToHex(h: number, s: number, l: number): string {
  const hex = hslChannels(h, s, l)
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("");
  return `#${hex}`;
}

function hslToRgbStr(h: number, s: number, l: number, alpha: number): string {
  const [r, g, b] = hslChannels(h, s, l);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ── Effect application ───────────────────────────────────────────────────────
// Writes the live tokens onto :root. The accent S/L are held near the stock
// ember so only warmth (hue) shifts — cooler toward red-clay, warmer toward gold.
function applyTweaks(density: DensityLevel, accentHue: number, liveness: number) {
  const root = document.documentElement.style;

  // — Density → spacing scale, panel padding, card gap, section rhythm —
  const k = DENSITY_SCALE[density];
  const base = [4, 8, 12, 16, 20, 24, 32, 40, 56, 80, 100];
  base.forEach((px, i) => root.setProperty(`--space-${i + 1}`, `${Math.round(px * k)}px`));
  root.setProperty("--panel-padding", `${Math.round(26 * k)}px`);
  root.setProperty("--card-gap", `${Math.round(16 * k)}px`);
  root.setProperty("--section-padding-y", `${Math.round(100 * k)}px`);
  // Local tokens consumed by the injected <style> below for surfaces whose
  // padding is hardcoded in app.css (content shell, metric/agent cards, rows).
  root.setProperty("--db-density-k", String(k));
  root.setProperty("--db-content-pad-y", `${Math.round(38 * k)}px`);
  root.setProperty("--db-content-pad-x", `${Math.round(44 * k)}px`);
  root.setProperty("--db-card-pad", `${Math.round(20 * k)}px`);

  // — Accent → hue shift of the single hero ember (S/L pinned to the brand) —
  const h = accentHue;
  root.setProperty("--accent", hslToHex(h, 85, 55));
  root.setProperty("--accent-soft", hslToHex(h, 88, 68));
  root.setProperty("--accent-deep", hslToHex(h, 84, 46));
  root.setProperty("--accent-glow", hslToRgbStr(h, 85, 55, 0.55));
  root.setProperty("--status-warn", hslToHex(h, 78, 44));
  root.setProperty("--status-warn-bg", hslToRgbStr(h, 85, 55, 0.12));

  // — Liveness → motion durations + animation speed multiplier —
  // 100 = snappy/vivid (short durations, fast loops); 0 = still (no anim).
  const v = liveness / 100;
  const dur = (ms: number) => `${Math.round(ms * (1.7 - v))}ms ease`;
  root.setProperty("--motion-fast", dur(150));
  root.setProperty("--motion-base", dur(200));
  root.setProperty("--motion-slow", dur(300));
  // Loop-animation period scale (pulse/aurora/blink). Higher liveness → faster.
  root.setProperty("--db-anim-scale", (1.7 - v).toFixed(3));
  root.setProperty("--db-anim-play", v <= 0.02 ? "paused" : "running");
}

function resetTokens() {
  const root = document.documentElement.style;
  [
    "--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6",
    "--space-7", "--space-8", "--space-9", "--space-10", "--space-11",
    "--panel-padding", "--card-gap", "--section-padding-y",
    "--db-density-k", "--db-content-pad-y", "--db-content-pad-x", "--db-card-pad",
    "--accent", "--accent-soft", "--accent-deep", "--accent-glow",
    "--status-warn", "--status-warn-bg",
    "--motion-fast", "--motion-base", "--motion-slow",
    "--db-anim-scale", "--db-anim-play",
  ].forEach((p) => root.removeProperty(p));
}

// Scoped overrides that route the design system's hardcoded paddings + loop
// animations through the tokens above, so Density and Liveness ripple to every
// surface — not just the ones already reading a variable. Lives here (this file
// owns it) instead of touching app.css.
const TWEAK_BRIDGE_CSS = `
  .db-content{padding:var(--db-content-pad-y,38px) var(--db-content-pad-x,44px) calc(var(--db-content-pad-y,38px) * 2.4) !important}
  .db-metric{padding:var(--db-card-pad,20px) calc(var(--db-card-pad,20px) + 2px) !important}
  .db-agent-card{padding:var(--db-card-pad,20px) !important}
  .db-status-dot.online::after,
  .status-chip.recovering::before,
  .eyebrow-pulse::before{
    animation-duration:calc(2s * var(--db-anim-scale,1)) !important;
    animation-play-state:var(--db-anim-play,running) !important}
  .db-trace-cursor{
    animation-duration:calc(1.1s * var(--db-anim-scale,1)) !important;
    animation-play-state:var(--db-anim-play,running) !important}
  .db-spin{animation-play-state:var(--db-anim-play,running) !important}
`;

// ── Panel chrome (ported from prototype tweaks-panel.jsx __TWEAKS_STYLE) ──────
const PANEL_CSS = `
  .twk-panel{position:fixed;right:18px;bottom:18px;z-index:2147483646;width:288px;
    max-height:calc(100vh - 36px);display:flex;flex-direction:column;
    background:rgba(248,245,240,.82);color:var(--ink-1,#18150f);
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:16px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 18px 50px -12px rgba(0,0,0,.28);
    font:12px/1.4 var(--font-sans,system-ui);overflow:hidden;
    animation:twk-in .22s cubic-bezier(.3,.7,.4,1)}
  @keyframes twk-in{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:13px 10px 12px 16px;cursor:move;user-select:none}
  .twk-hd-l{display:flex;align-items:center;gap:8px}
  .twk-hd-l b{font-size:12.5px;font-weight:600;letter-spacing:.01em}
  .twk-hd-l .twk-mark{display:flex;color:var(--accent,#ef6a2a)}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(24,21,15,.5);
    width:24px;height:24px;border-radius:7px;cursor:pointer;display:flex;
    align-items:center;justify-content:center;transition:background .15s,color .15s}
  .twk-x:hover{background:rgba(0,0,0,.06);color:var(--ink-1,#18150f)}
  .twk-body{padding:2px 16px 16px;display:flex;flex-direction:column;gap:12px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-sect{font-family:var(--font-mono,monospace);font-size:9.5px;font-weight:500;
    letter-spacing:.12em;text-transform:uppercase;color:rgba(24,21,15,.42);padding:10px 0 0}
  .twk-sect:first-child{padding-top:2px}
  .twk-row{display:flex;flex-direction:column;gap:6px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;color:rgba(24,21,15,.74)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:var(--accent,#ef6a2a);font-family:var(--font-mono,monospace);
    font-size:11px;font-variant-numeric:tabular-nums}
  .twk-hint{font-size:10.5px;line-height:1.4;color:rgba(24,21,15,.42)}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:5px 0 2px;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none;cursor:pointer}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:15px;height:15px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.25),0 0 0 0 var(--accent-glow);
    cursor:pointer;transition:box-shadow .15s}
  .twk-slider:hover::-webkit-slider-thumb{box-shadow:0 1px 3px rgba(0,0,0,.25),0 0 0 4px var(--accent-glow)}
  .twk-slider::-moz-range-thumb{width:15px;height:15px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.25);cursor:pointer}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:9px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:7px;
    background:rgba(255,255,255,.92);box-shadow:0 1px 2px rgba(0,0,0,.14);
    transition:left .18s cubic-bezier(.3,.7,.4,1),width .18s}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:24px;
    border-radius:7px;cursor:pointer;padding:5px 6px;line-height:1.2;transition:color .15s}
  .twk-seg button[aria-checked="false"]{color:rgba(24,21,15,.5)}

  .twk-swatches{display:flex;gap:7px}
  .twk-swatch{position:relative;appearance:none;flex:1;height:30px;padding:0;border:0;
    border-radius:8px;cursor:pointer;box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.07);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-swatch:hover{transform:translateY(-1px);box-shadow:0 0 0 .5px rgba(0,0,0,.2),0 4px 10px rgba(0,0,0,.14)}
  .twk-swatch[data-on="1"]{box-shadow:0 0 0 2px var(--ink-1,#18150f),0 2px 6px rgba(0,0,0,.18)}
  .twk-swatch svg{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
    width:15px;height:15px;color:#fff;filter:drop-shadow(0 1px 1px rgba(0,0,0,.35))}

  .twk-foot{display:flex;justify-content:flex-end;padding-top:2px}
  .twk-reset{appearance:none;display:inline-flex;align-items:center;gap:5px;
    border:0;background:transparent;color:rgba(24,21,15,.5);font:inherit;font-size:11px;
    padding:4px 6px;border-radius:6px;cursor:pointer;transition:background .15s,color .15s}
  .twk-reset:hover{background:rgba(0,0,0,.06);color:var(--ink-1,#18150f)}
`;

// Curated accent-mood swatches — each is a hue (deg) on the ember spectrum,
// from red-clay (cool) through stock ember to amber-gold (warm).
const ACCENT_MOODS: { hue: number; label: string }[] = [
  { hue: 8, label: "Clay" },
  { hue: 18, label: "Ember" },
  { hue: 30, label: "Amber" },
  { hue: 42, label: "Gold" },
];

function Slider({
  label, value, min, max, step = 1, display, onChange,
}: {
  label: string; value: number; min: number; max: number; step?: number;
  display: ReactNode; onChange: (v: number) => void;
}) {
  return (
    <div className="twk-row">
      <div className="twk-lbl">
        <span>{label}</span>
        <span className="twk-val">{display}</span>
      </div>
      <input
        type="range" className="twk-slider" min={min} max={max} step={step}
        value={value} onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

function Segmented({
  label, value, options, onChange,
}: {
  label: string; value: number; options: readonly string[]; onChange: (i: number) => void;
}) {
  const n = options.length;
  return (
    <div className="twk-row">
      <div className="twk-lbl"><span>{label}</span></div>
      <div className="twk-seg" role="radiogroup" aria-label={label}>
        <div
          className="twk-seg-thumb"
          style={{ left: `calc(2px + ${value} * (100% - 4px) / ${n})`, width: `calc((100% - 4px) / ${n})` }}
        />
        {options.map((o, i) => (
          <button
            key={o} type="button" role="radio" aria-checked={value === i}
            onClick={() => onChange(i)}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Tweaks() {
  const open = useUI((s) => s.tweaksOpen);
  const setTweaks = useUI((s) => s.setTweaks);

  const [density, setDensity] = useState<DensityLevel>(DENSITY_DEFAULT);
  const [accent, setAccent] = useState(ACCENT_DEFAULT);
  const [liveness, setLiveness] = useState(LIVENESS_DEFAULT);

  // Apply live whenever a control changes (panel stays mounted-but-hidden, so the
  // tokens persist after closing — operators keep their chosen feel).
  useEffect(() => {
    applyTweaks(density, accent, liveness);
  }, [density, accent, liveness]);

  // Restore stock tokens if the panel unmounts entirely.
  useEffect(() => () => resetTokens(), []);

  // Esc closes, matching the other overlays (Modal/palette).
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") setTweaks(false); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, setTweaks]);

  // Drag-to-reposition (ported from the prototype's floating-panel behaviour).
  const panelRef = useRef<HTMLDivElement>(null);
  const posRef = useRef({ right: 18, bottom: 18 });
  const onDragStart = (e: React.MouseEvent) => {
    const panel = panelRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX, sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = (ev: MouseEvent) => {
      const w = panel.offsetWidth, h = panel.offsetHeight;
      const right = Math.min(Math.max(8, startRight - (ev.clientX - sx)), window.innerWidth - w - 8);
      const bottom = Math.min(Math.max(8, startBottom - (ev.clientY - sy)), window.innerHeight - h - 8);
      posRef.current = { right, bottom };
      panel.style.right = `${right}px`;
      panel.style.bottom = `${bottom}px`;
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  if (!open) {
    // Keep the bridge style mounted so chosen tokens still resolve while closed.
    return <style>{TWEAK_BRIDGE_CSS}</style>;
  }

  const reset = () => {
    setDensity(DENSITY_DEFAULT);
    setAccent(ACCENT_DEFAULT);
    setLiveness(LIVENESS_DEFAULT);
  };

  const livenessLabel = liveness <= 2 ? "still" : liveness >= 92 ? "vivid" : `${liveness}`;

  return (
    <>
      <style>{PANEL_CSS}</style>
      <style>{TWEAK_BRIDGE_CSS}</style>
      <div
        ref={panelRef} className="twk-panel" role="dialog" aria-label="Tweaks"
        style={{ right: posRef.current.right, bottom: posRef.current.bottom }}
      >
        <div className="twk-hd" onMouseDown={onDragStart}>
          <div className="twk-hd-l">
            <span className="twk-mark"><Icon name="sliders" size={15} stroke={2} /></span>
            <b>Tweaks</b>
          </div>
          <button
            className="twk-x" aria-label="Close tweaks"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => setTweaks(false)}
          >
            <Icon name="x" size={14} stroke={2} />
          </button>
        </div>
        <div className="twk-body">
          <div className="twk-sect">Density</div>
          <Segmented
            label="Spacing" value={density} options={DENSITY_OPTS}
            onChange={(i) => setDensity(i as DensityLevel)}
          />
          <div className="twk-hint">
            From a calm dashboard to a tight mission-control wall.
          </div>

          <div className="twk-sect">Accent mood</div>
          <div className="twk-row">
            <div className="twk-lbl">
              <span>Warmth</span>
              <span className="twk-val">{accent}°</span>
            </div>
            <div className="twk-swatches" role="radiogroup" aria-label="Accent mood">
              {ACCENT_MOODS.map((m) => {
                const on = accent === m.hue;
                return (
                  <button
                    key={m.hue} type="button" className="twk-swatch" role="radio"
                    aria-checked={on} aria-label={m.label} title={m.label} data-on={on ? "1" : "0"}
                    style={{ background: hslToHex(m.hue, 85, 55) }}
                    onClick={() => setAccent(m.hue)}
                  >
                    {on && <Icon name="check" size={15} stroke={2.4} />}
                  </button>
                );
              })}
            </div>
          </div>
          <Slider
            label="Fine-tune" value={accent} min={2} max={48} display={`${accent}°`}
            onChange={setAccent}
          />

          <div className="twk-sect">Liveness</div>
          <Slider
            label="Motion" value={liveness} min={0} max={100} display={livenessLabel}
            onChange={setLiveness}
          />
          <div className="twk-hint">
            How alive the surface feels — animation speed, pulses and transitions.
          </div>

          <div className="twk-foot">
            <button type="button" className="twk-reset" onClick={reset}>
              <Icon name="rotate-ccw" size={12} stroke={2} />
              Reset
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
