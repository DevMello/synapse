// Top bar — flow name, status, live validation summary, zoom, and the Test / Save /
// Publish actions. Publish is disabled while the graph has validation errors.
import { Icon } from "../../../components/Primitives";
import type { FlowGraph } from "../useFlowGraph";
import type { FlowIssue } from "../validate";
import type { FlowStatus } from "../../../types";

interface Props {
  graph: FlowGraph;
  status: FlowStatus;
  issues: FlowIssue[];
  saving: boolean;
  testing: boolean;
  tracing: boolean;
  onBack: () => void;
  onTest: () => void;
  onSave: () => void;
  onPublish: () => void;
}

export default function Toolbar({
  graph, status, issues, saving, testing, tracing, onBack, onTest, onSave, onPublish,
}: Props) {
  const errors = issues.filter((i) => i.level === "error").length;
  const warns = issues.filter((i) => i.level === "warn").length;
  const z = Math.round(graph.view.zoom * 100);

  return (
    <div className="fc-toolbar">
      <div className="fc-tb-left">
        <button className="fc-tb-icon" title="Back to flows" onClick={onBack}>
          <Icon name="arrow-left" size={16} />
        </button>
        <input
          className="fc-tb-name"
          value={graph.name}
          spellCheck={false}
          onChange={(e) => graph.setName(e.target.value)}
        />
        <span className={"fc-status fc-status--" + status}>{status}</span>
        {graph.dirty && <span className="fc-dirty" title="Unsaved changes">●</span>}
      </div>

      <div className="fc-tb-mid">
        {errors > 0 ? (
          <span className="fc-valid fc-valid--err"><Icon name="alert-triangle" size={13} /> {errors} {errors === 1 ? "issue" : "issues"}</span>
        ) : (
          <span className="fc-valid fc-valid--ok"><Icon name="check" size={13} /> valid chain</span>
        )}
        {warns > 0 && <span className="fc-valid fc-valid--warn"><Icon name="info" size={13} /> {warns}</span>}
      </div>

      <div className="fc-tb-right">
        <div className="fc-zoom">
          <button onClick={() => graph.zoomAt(0.9, 300, 200)} title="Zoom out"><Icon name="minus" size={14} /></button>
          <button className="fc-zoom-val" onClick={graph.resetView} title="Reset view">{z}%</button>
          <button onClick={() => graph.zoomAt(1.1, 300, 200)} title="Zoom in"><Icon name="plus" size={14} /></button>
        </div>
        <button className="db-btn outline-light" onClick={onTest} disabled={testing || tracing}>
          <Icon name="play" size={14} /> {testing ? "Testing…" : "Test flow"}
        </button>
        <button className="db-btn outline-light" onClick={onSave} disabled={saving || !graph.dirty}>
          <Icon name="save" size={14} /> {saving ? "Saving…" : "Save"}
        </button>
        <button className="db-btn primary" onClick={onPublish} disabled={errors > 0}>
          <Icon name="shield" size={14} /> Publish
        </button>
      </div>
    </div>
  );
}
