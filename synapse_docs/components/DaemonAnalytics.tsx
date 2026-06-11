'use client'

import { useMemo, useState } from 'react'

// Per (agent, model) aggregate rows for the `dev-laptop` daemon over the
// last 30 days. Every metric on the dashboard is derived from these rows so
// the agent filter always stays internally consistent.
type Row = {
  agent: string
  type: 'API Model' | 'CLI Tool'
  model: string
  runs: number
  inputTokens: number
  outputTokens: number
  cost: number // USD
  toolCalls: number
  avgLatencyMs: number
  passed: number
}

const ROWS: Row[] = [
  { agent: 'pr-reviewer', type: 'API Model', model: 'claude-opus-4-8', runs: 142, inputTokens: 4_820_000, outputTokens: 612_000, cost: 41.18, toolCalls: 388, avgLatencyMs: 14_300, passed: 137 },
  { agent: 'gh-triage', type: 'API Model', model: 'claude-sonnet-4-6', runs: 906, inputTokens: 7_240_000, outputTokens: 488_000, cost: 18.42, toolCalls: 1_812, avgLatencyMs: 6_100, passed: 881 },
  { agent: 'nightly-summarizer', type: 'API Model', model: 'claude-haiku-4-5', runs: 30, inputTokens: 1_960_000, outputTokens: 240_000, cost: 2.18, toolCalls: 0, avgLatencyMs: 9_400, passed: 30 },
  { agent: 'codex-refactor', type: 'CLI Tool', model: 'claude-sonnet-4-6', runs: 64, inputTokens: 9_120_000, outputTokens: 1_040_000, cost: 42.96, toolCalls: 2_944, avgLatencyMs: 212_000, passed: 58 },
  { agent: 'codex-refactor', type: 'CLI Tool', model: 'claude-opus-4-8', runs: 18, inputTokens: 2_640_000, outputTokens: 410_000, cost: 26.55, toolCalls: 920, avgLatencyMs: 268_000, passed: 16 },
]

const AGENTS = ['All agents', ...Array.from(new Set(ROWS.map((r) => r.agent)))]

const usd = (n: number) =>
  n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`

const compact = (n: number) => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return `${n}`
}

const latency = (ms: number) =>
  ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`

const MODEL_COLORS: Record<string, string> = {
  'claude-opus-4-8': 'var(--accent)',
  'claude-sonnet-4-6': 'var(--status-info)',
  'claude-haiku-4-5': 'var(--status-ok)',
}

export default function DaemonAnalytics() {
  const [agent, setAgent] = useState('All agents')

  const rows = useMemo(
    () => (agent === 'All agents' ? ROWS : ROWS.filter((r) => r.agent === agent)),
    [agent],
  )

  const totals = useMemo(() => {
    const runs = rows.reduce((s, r) => s + r.runs, 0)
    const inputTokens = rows.reduce((s, r) => s + r.inputTokens, 0)
    const outputTokens = rows.reduce((s, r) => s + r.outputTokens, 0)
    const cost = rows.reduce((s, r) => s + r.cost, 0)
    const toolCalls = rows.reduce((s, r) => s + r.toolCalls, 0)
    const passed = rows.reduce((s, r) => s + r.passed, 0)
    // run-weighted average latency
    const avgLatencyMs = runs ? rows.reduce((s, r) => s + r.avgLatencyMs * r.runs, 0) / runs : 0
    return {
      runs,
      inputTokens,
      outputTokens,
      tokens: inputTokens + outputTokens,
      cost,
      toolCalls,
      avgLatencyMs,
      costPerRun: runs ? cost / runs : 0,
      successRate: runs ? (passed / runs) * 100 : 0,
    }
  }, [rows])

  // Cost rolled up by model for the current filter.
  const byModel = useMemo(() => {
    const map = new Map<string, { model: string; runs: number; tokens: number; cost: number; toolCalls: number }>()
    for (const r of rows) {
      const cur = map.get(r.model) ?? { model: r.model, runs: 0, tokens: 0, cost: 0, toolCalls: 0 }
      cur.runs += r.runs
      cur.tokens += r.inputTokens + r.outputTokens
      cur.cost += r.cost
      cur.toolCalls += r.toolCalls
      map.set(r.model, cur)
    }
    return [...map.values()].sort((a, b) => b.cost - a.cost)
  }, [rows])

  const maxModelCost = Math.max(...byModel.map((m) => m.cost), 0.0001)
  const inputPct = totals.tokens ? (totals.inputTokens / totals.tokens) * 100 : 0

  const stats = [
    { label: 'Total tokens', value: compact(totals.tokens), caption: `${compact(totals.inputTokens)} in · ${compact(totals.outputTokens)} out` },
    { label: 'Spend (30d)', value: usd(totals.cost), caption: `${usd(totals.costPerRun)} avg / run` },
    { label: 'Avg latency', value: latency(totals.avgLatencyMs), caption: `across ${totals.runs.toLocaleString()} runs` },
    { label: 'Tool calls', value: totals.toolCalls.toLocaleString(), caption: `${totals.successRate.toFixed(1)}% runs passed` },
  ]

  return (
    <div className="dmn-analytics">
      <div className="dmn-an-toolbar">
        <div className="dmn-an-filter">
          <label htmlFor="dmn-agent">Agent</label>
          <select id="dmn-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
            {AGENTS.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
        <span className="dmn-an-scope">
          dev-laptop · {agent === 'All agents' ? `${AGENTS.length - 1} agents` : '1 agent'} · last 30 days
        </span>
      </div>

      <div className="dmn-an-stats">
        {stats.map((s) => (
          <div className="stat-card" key={s.label}>
            <div className="stat-label">{s.label}</div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-caption">{s.caption}</div>
          </div>
        ))}
      </div>

      <div className="dmn-an-split">
        <div className="surface dmn-an-card">
          <div className="dmn-an-card-head">
            <h4>Cost by model</h4>
            <span>{byModel.length} {byModel.length === 1 ? 'model' : 'models'}</span>
          </div>
          <div className="dmn-an-bars">
            {byModel.map((m) => (
              <div className="dmn-an-bar-row" key={m.model}>
                <div className="dmn-an-bar-meta">
                  <span className="dmn-an-dot" style={{ background: MODEL_COLORS[m.model] ?? 'var(--mute)' }} />
                  <code>{m.model}</code>
                  <span className="dmn-an-bar-cost">{usd(m.cost)}</span>
                </div>
                <div className="dmn-an-track">
                  <div
                    className="dmn-an-fill"
                    style={{ width: `${(m.cost / maxModelCost) * 100}%`, background: MODEL_COLORS[m.model] ?? 'var(--mute)' }}
                  />
                </div>
                <div className="dmn-an-bar-sub">
                  {m.runs.toLocaleString()} runs · {compact(m.tokens)} tokens · {m.toolCalls.toLocaleString()} tool calls
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="surface dmn-an-card">
          <div className="dmn-an-card-head">
            <h4>Token split</h4>
            <span>{compact(totals.tokens)} total</span>
          </div>
          <div className="dmn-an-track dmn-an-track-lg">
            <div className="dmn-an-fill" style={{ width: `${inputPct}%`, background: 'var(--status-info)' }} />
            <div className="dmn-an-fill" style={{ width: `${100 - inputPct}%`, background: 'var(--accent)' }} />
          </div>
          <div className="dmn-an-legend">
            <span><i style={{ background: 'var(--status-info)' }} />Input · {compact(totals.inputTokens)} ({inputPct.toFixed(0)}%)</span>
            <span><i style={{ background: 'var(--accent)' }} />Output · {compact(totals.outputTokens)} ({(100 - inputPct).toFixed(0)}%)</span>
          </div>
          <dl className="dmn-an-kv">
            <div><dt>Runs</dt><dd>{totals.runs.toLocaleString()}</dd></div>
            <div><dt>Success rate</dt><dd>{totals.successRate.toFixed(1)}%</dd></div>
            <div><dt>Cost / 1M tokens</dt><dd>{usd(totals.tokens ? (totals.cost / totals.tokens) * 1_000_000 : 0)}</dd></div>
          </dl>
        </div>
      </div>

      <div className="table-card dmn-an-table">
        <table className="compact-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Type</th>
              <th>Model</th>
              <th style={{ textAlign: 'right' }}>Runs</th>
              <th style={{ textAlign: 'right' }}>Tokens</th>
              <th style={{ textAlign: 'right' }}>Avg latency</th>
              <th style={{ textAlign: 'right' }}>Tool calls</th>
              <th style={{ textAlign: 'right' }}>Spend</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.agent}-${r.model}`}>
                <td><code>{r.agent}</code></td>
                <td>{r.type}</td>
                <td><code>{r.model}</code></td>
                <td style={{ textAlign: 'right' }}>{r.runs.toLocaleString()}</td>
                <td style={{ textAlign: 'right' }}>{compact(r.inputTokens + r.outputTokens)}</td>
                <td style={{ textAlign: 'right' }}>{latency(r.avgLatencyMs)}</td>
                <td style={{ textAlign: 'right' }}>{r.toolCalls.toLocaleString()}</td>
                <td style={{ textAlign: 'right' }}>{usd(r.cost)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}><strong>{agent === 'All agents' ? 'All agents' : agent}</strong></td>
              <td style={{ textAlign: 'right' }}><strong>{totals.runs.toLocaleString()}</strong></td>
              <td style={{ textAlign: 'right' }}><strong>{compact(totals.tokens)}</strong></td>
              <td style={{ textAlign: 'right' }}><strong>{latency(totals.avgLatencyMs)}</strong></td>
              <td style={{ textAlign: 'right' }}><strong>{totals.toolCalls.toLocaleString()}</strong></td>
              <td style={{ textAlign: 'right' }}><strong>{usd(totals.cost)}</strong></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}
