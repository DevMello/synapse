// Agent Detail — Memory tab. A searchable, editable, redaction-aware table of the
// agent's persistent memory (key / value / namespace / tags / size). Edits, deletes
// and pre-loads round-trip to the daemon via memory.sync (mocked here as toasts).
// Ported from the prototype's MemoryTab (design-reference/app/AgentTabs3.jsx) + §4.17.
import { useEffect, useMemo, useState } from "react";
import { Button, Icon } from "../../../components/Primitives";
import { MetricCard, Modal, Segmented, ConfirmDialog } from "../../../components/Common";
import { useMemory } from "../../../api/queries";
import { useUI } from "../../../store/ui";
import { useCurrentAgent } from "../context";
import type { MemoryEntry } from "../../../types";

type Provider = "sqlite" | "vector";

// Parse "0.3 KB" / "50 MB" → kilobytes, so the footprint metric can sum mixed units.
function sizeToKB(size: string): number {
  const m = /([\d.]+)\s*(KB|MB|GB)/i.exec(size);
  if (!m) return 0;
  const n = parseFloat(m[1]);
  const unit = m[2].toUpperCase();
  return unit === "GB" ? n * 1024 * 1024 : unit === "MB" ? n * 1024 : n;
}

function formatKB(kb: number): { n: string; unit: string } {
  if (kb >= 1024 * 1024) return { n: (kb / 1024 / 1024).toFixed(1), unit: "GB" };
  if (kb >= 1024) return { n: (kb / 1024).toFixed(1), unit: "MB" };
  return { n: kb.toFixed(1), unit: "KB" };
}

export default function MemoryTab() {
  useCurrentAgent(); // anchors the tab to the routed agent (one store per agent).
  const { data: memory = [] } = useMemory();
  const showToast = useUI((s) => s.showToast);

  // Adopt the asynchronously-resolved query data once it arrives (it is [] on the
  // first render); thereafter we mutate `rows` locally for edit/delete/pre-load.
  const [rows, setRows] = useState<MemoryEntry[]>(memory);
  useEffect(() => {
    setRows(memory);
  }, [memory]);

  const [q, setQ] = useState("");
  const [provider, setProvider] = useState<Provider>("vector");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<MemoryEntry | null>(null);
  const [preloadOpen, setPreloadOpen] = useState(false);
  const [preloadText, setPreloadText] = useState("");

  const filtered = useMemo(
    () =>
      rows.filter(
        (r) =>
          !q.trim() ||
          (r.key + r.val + r.tags.join(" ")).toLowerCase().includes(q.toLowerCase()),
      ),
    [rows, q],
  );

  const footprint = useMemo(
    () => formatKB(rows.reduce((sum, r) => sum + sizeToKB(r.size), 0)),
    [rows],
  );

  function commitEdit(entry: MemoryEntry) {
    setRows((rs) => rs.map((x) => (x.key === entry.key ? { ...x, val: draft } : x)));
    setEditing(null);
    showToast({ text: `${entry.key} corrected — synced to daemon` });
  }

  function deleteEntry(entry: MemoryEntry) {
    setRows((rs) => rs.filter((x) => x.key !== entry.key));
    setConfirmDelete(null);
    showToast({ text: `${entry.key} deleted — synced to daemon`, variant: "warn" });
  }

  // Pre-load / bulk-add: one `key: value` per line. Seeds rows before first run.
  function commitPreload() {
    const added: MemoryEntry[] = [];
    for (const line of preloadText.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const idx = trimmed.indexOf(":");
      const key = idx >= 0 ? trimmed.slice(0, idx).trim() : trimmed;
      const val = idx >= 0 ? trimmed.slice(idx + 1).trim() : "";
      if (!key) continue;
      const size = `${(new Blob([val]).size / 1024).toFixed(1)} KB`;
      added.push({ key, ns: "seed", val, tags: ["preload"], size, updated: "just now" });
    }
    if (added.length) {
      setRows((rs) => {
        const byKey = new Map(rs.map((r) => [r.key, r]));
        for (const a of added) byKey.set(a.key, a);
        return Array.from(byKey.values());
      });
      showToast({ text: `Pre-loaded ${added.length} ${added.length === 1 ? "entry" : "entries"} — syncing to daemon` });
    }
    setPreloadOpen(false);
    setPreloadText("");
  }

  return (
    <div className="db-memory">
      <div className="db-callout">
        <Icon name="brain" size={16} />
        <span>
          <b>Visible by design.</b> Memory is redacted on-device before sync and stored
          cloud-side as RLS-scoped plaintext — not E2E-encrypted — so you can read and fix
          it. Secrets belong in <b>Environment</b>, never here.
        </span>
      </div>

      <div className="db-metric-grid db-metric-grid-3">
        <MetricCard label="Entries" n={rows.length} sub="this agent" />
        <MetricCard label="Footprint" n={footprint.n} unit={footprint.unit} delta="+4 MB this week" dir="up" />
        <MetricCard
          label="Provider"
          n={provider === "vector" ? "vector" : "sqlite"}
          sub={provider === "vector" ? "Qdrant · semantic recall" : "sqlite-memory"}
        />
      </div>

      <div className="db-toolbar">
        <div className="db-search-inline">
          <Icon name="search" size={15} style={{ color: "var(--mute)" }} />
          <input
            placeholder="Search keys, values, tags… (semantic on vector)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="db-toolbar-r">
          <Segmented<Provider>
            value={provider}
            onChange={(v) => {
              setProvider(v);
              showToast({
                text:
                  v === "vector"
                    ? "Storage provider → vector-memory (Qdrant) — semantic recall"
                    : "Storage provider → sqlite-memory",
              });
            }}
            options={[
              { value: "sqlite", label: "sqlite-memory" },
              { value: "vector", label: "vector-memory" },
            ]}
          />
          <Button variant="outline-light" icon="upload" onClick={() => setPreloadOpen(true)}>
            Pre-load
          </Button>
        </div>
      </div>

      <div className="db-table-wrap">
        <table className="db-table db-mem-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Value</th>
              <th>Namespace</th>
              <th>Tags</th>
              <th>Size</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.key}>
                <td className="db-cell-primary db-mono">{r.key}</td>
                <td className="db-mem-val">
                  {editing === r.key ? (
                    <input
                      className="db-input-sm"
                      autoFocus
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit(r);
                        if (e.key === "Escape") setEditing(null);
                      }}
                      onBlur={() => setEditing(null)}
                    />
                  ) : (
                    r.val
                  )}
                </td>
                <td className="db-mono">
                  <span className="db-ns-pill">{r.ns}</span>
                </td>
                <td>
                  {r.tags.map((t) => (
                    <span key={t} className="db-tag">
                      {t}
                    </span>
                  ))}
                </td>
                <td className="db-mono db-muted">{r.size}</td>
                <td>
                  <div className="db-env-row-actions">
                    <button
                      className="db-icon-mini"
                      title="Edit"
                      onClick={() => {
                        setEditing(r.key);
                        setDraft(r.val);
                      }}
                    >
                      <Icon name="pencil" size={14} />
                    </button>
                    <button
                      className="db-icon-mini danger"
                      title="Delete"
                      onClick={() => setConfirmDelete(r)}
                    >
                      <Icon name="trash" size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="db-muted db-mono" style={{ textAlign: "center" }}>
                  {rows.length === 0 ? "No memory entries yet." : "No entries match your search."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="db-env-foot db-mono">
        <Icon name="refresh-cw" size={12} /> Reads come from the cloud snapshot (synced on
        demand). Edits round-trip to the daemon's local store — the source of truth.
      </div>

      <Modal open={preloadOpen} onClose={() => setPreloadOpen(false)} width={560}>
        <div className="db-dialog">
          <div className="db-dialog-icon">
            <Icon name="upload" size={20} />
          </div>
          <h3 className="db-dialog-title">Pre-load memory</h3>
          <div className="db-dialog-body">
            Bulk-add seed entries before the first run — one <span className="db-mono">key: value</span>{" "}
            per line. The cloud syncs them down to the daemon's local provider.
          </div>
          <textarea
            className="db-input-sm"
            style={{ minHeight: 140, resize: "vertical", marginBottom: 16, fontFamily: "var(--font-mono)" }}
            placeholder={"fact/deploy-target: Production runs on fly.io, region iad.\npref/commit-style: Conventional commits, imperative mood."}
            value={preloadText}
            onChange={(e) => setPreloadText(e.target.value)}
          />
          <div className="db-dialog-actions">
            <Button variant="outline-light" onClick={() => setPreloadOpen(false)}>
              Cancel
            </Button>
            <button className="btn btn-primary" onClick={commitPreload} disabled={!preloadText.trim()}>
              Pre-load
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDelete != null}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => confirmDelete && deleteEntry(confirmDelete)}
        title="Delete memory entry?"
        body={
          <>
            <span className="db-mono">{confirmDelete?.key}</span> will be removed and the
            deletion synced to the daemon's local store. This can't be undone.
          </>
        }
        confirmLabel="Delete"
        danger
      />
    </div>
  );
}
