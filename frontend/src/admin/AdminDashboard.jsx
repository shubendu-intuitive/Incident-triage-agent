import { useEffect, useState, useRef, useCallback } from 'react'

const API = 'http://localhost:8000'

// ── Colour maps ───────────────────────────────────────────────────────────────
const CAT_COLOR  = { llm: '#8b5cf6', tool: '#14b8a6', hitl: '#f59e0b', routing: '#475569' }
const TOOL_COLOR = { investigation: '#14b8a6', diagnosis: '#8b5cf6', fix: '#f59e0b', verify: '#22c55e' }
const NODE_POS   = {
  plan_investigation:         { x: 340, y: 40  },
  run_parallel_investigation: { x: 340, y: 120 },
  analyse_initial_findings:   { x: 340, y: 200 },
  deep_diagnosis:             { x: 155, y: 290 },
  fetch_runbook:              { x: 340, y: 290 },
  decide_action:              { x: 340, y: 370 },
  execute_fix:                { x: 155, y: 460 },
  human_checkpoint:           { x: 340, y: 460 },
  cannot_fix:                 { x: 525, y: 460 },
  execute_approved_fix:       { x: 340, y: 550 },
  verify_outcome:             { x: 340, y: 630 },
  generate_report:            { x: 340, y: 710 },
}
const NW = 130, NH = 34

// ── Small reusable pieces ─────────────────────────────────────────────────────
function Badge({ label, color }) {
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium"
      style={{ background: color + '20', color, border: `1px solid ${color}40` }}>
      {label}
    </span>
  )
}

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false)
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
      className="text-xs text-slate-500 hover:text-slate-300 px-2 py-0.5 border border-slate-700 rounded transition-colors">
      {copied ? '✓ copied' : 'copy'}
    </button>
  )
}

function Collapsible({ label, children, defaultOpen = false, right }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-slate-900 hover:bg-slate-800 transition-colors">
        <span className="text-xs font-medium text-slate-400">{open ? '▾' : '▸'} {label}</span>
        <div className="flex items-center gap-2">{right}</div>
      </button>
      {open && <div className="bg-slate-950">{children}</div>}
    </div>
  )
}

function CodeBlock({ text, maxH = '280px' }) {
  if (!text) return <div className="p-3 text-xs text-slate-600 italic">— empty —</div>
  return (
    <pre className="p-3 text-xs text-slate-300 leading-relaxed whitespace-pre-wrap overflow-auto font-mono"
      style={{ maxHeight: maxH }}>
      {text}
    </pre>
  )
}

// ── Graph tab ─────────────────────────────────────────────────────────────────
function GraphTab({ graphData, activeNode, completedNodes }) {
  if (!graphData) return <p className="text-slate-500 text-sm p-4">Loading graph…</p>

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Live state machine</div>
      <div className="overflow-auto">
        <svg width="100%" viewBox="0 0 680 780" style={{ minWidth: 300 }}>
          <defs>
            <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M2 1L8 5L2 9" fill="none" stroke="#475569" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </marker>
          </defs>
          {graphData.edges.map((e, i) => {
            const f = NODE_POS[e.from], t = NODE_POS[e.to]
            if (!f || !t) return null
            const traversed = completedNodes.includes(e.from) && completedNodes.includes(e.to)
            const x1 = f.x, y1 = f.y + NH, x2 = t.x, y2 = t.y
            const d = Math.abs(x1 - x2) < 5
              ? `M ${x1} ${y1} L ${x2} ${y2}`
              : `M ${x1} ${y1} C ${x1} ${(y1+y2)/2} ${x2} ${(y1+y2)/2} ${x2} ${y2}`
            return <path key={i} d={d} fill="none"
              stroke={traversed ? '#14b8a6' : '#334155'}
              strokeWidth={traversed ? 1.5 : 0.5}
              strokeDasharray={e.type === 'conditional' ? '4 3' : 'none'}
              markerEnd="url(#arr)" />
          })}
          {graphData.nodes.map(n => {
            const pos = NODE_POS[n.id]
            if (!pos) return null
            const active    = activeNode === n.id
            const completed = completedNodes.includes(n.id)
            const col = CAT_COLOR[n.category] || '#475569'
            return (
              <g key={n.id}>
                {active && <rect x={pos.x-NW/2-4} y={pos.y-4} width={NW+8} height={NH+8} rx="10"
                  fill={col+'15'} stroke={col} strokeWidth="1.5"
                  style={{ filter: `drop-shadow(0 0 8px ${col})` }} />}
                <rect x={pos.x-NW/2} y={pos.y} width={NW} height={NH} rx="6"
                  fill={active ? col : completed ? col+'35' : '#1e293b'}
                  stroke={active || completed ? col : '#334155'}
                  strokeWidth={active ? 2 : 0.5} />
                <text x={pos.x} y={pos.y+NH/2+1} textAnchor="middle" dominantBaseline="central"
                  fill={active ? '#fff' : completed ? col : '#64748b'}
                  fontSize="11" fontWeight={active ? 600 : 400}>
                  {active ? '▶ ' : completed ? '✓ ' : ''}{n.label}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      <div className="flex flex-wrap gap-4 mt-2 pt-3 border-t border-slate-800">
        {Object.entries(CAT_COLOR).map(([k, c]) => (
          <div key={k} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />
            <span className="text-xs text-slate-500">{k}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── System tab ────────────────────────────────────────────────────────────────
function SystemTab({ info }) {
  if (!info) return <p className="text-slate-500 text-sm p-4">Loading…</p>
  const sys = info.system || {}

  function Bar({ value, color }) {
    return (
      <div className="h-2 bg-slate-800 rounded overflow-hidden mt-1">
        <div className="h-full rounded transition-all duration-700"
          style={{ width: `${Math.min(value, 100)}%`, background: color }} />
      </div>
    )
  }
  function Row({ label, value }) {
    return (
      <div className="flex justify-between items-center py-1 border-b border-slate-800/50">
        <span className="text-xs text-slate-500">{label}</span>
        <span className="text-xs font-mono text-slate-300">{value}</span>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">LLM configuration</div>
        <Row label="Provider"  value={<span className="text-blue-400">{info.llm_provider}</span>} />
        <Row label="Model"     value={info.llm_model} />
        <Row label="Mode"      value={info.mode} />
        <Row label="Ollama"    value={info.ollama_online
          ? <span className="text-green-400">● online</span>
          : <span className="text-red-400">● offline</span>} />
      </div>

      {info.ollama_model_detail && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Model detail</div>
          <Row label="Parameters"   value={info.ollama_model_detail.parameter_size} />
          <Row label="Quantization" value={info.ollama_model_detail.quantization} />
          <Row label="Format"       value={info.ollama_model_detail.format} />
          <Row label="Size on disk" value={`${info.ollama_model_detail.size_gb} GB`} />
        </div>
      )}

      {sys.cpu_percent !== undefined && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">System resources</div>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">CPU</span>
                <span className="text-slate-300">{sys.cpu_percent}%</span>
              </div>
              <Bar value={sys.cpu_percent} color={sys.cpu_percent > 80 ? '#ef4444' : '#3b82f6'} />
            </div>
            <div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">RAM  {sys.ram_used_gb} / {sys.ram_total_gb} GB</span>
                <span className="text-slate-300">{sys.ram_percent}%</span>
              </div>
              <Bar value={sys.ram_percent} color={sys.ram_percent > 85 ? '#ef4444' : '#8b5cf6'} />
            </div>
            <Row label="Available" value={`${sys.ram_available_gb} GB`} />
          </div>
        </div>
      )}

      {info.ollama_models?.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Installed models</div>
          <div className="space-y-1.5">
            {info.ollama_models.map(m => (
              <div key={m.name} className="flex justify-between text-xs">
                <span className={`font-mono ${info.llm_model && m.name.includes(info.llm_model.split(':')[0]) ? 'text-green-400' : 'text-slate-500'}`}>
                  {info.llm_model && m.name.includes(info.llm_model.split(':')[0]) ? '▶ ' : '   '}{m.name}
                </span>
                <span className="text-slate-600">{m.size_gb} GB</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tools tab ─────────────────────────────────────────────────────────────────
function ToolsTab({ runId }) {
  const [tools, setTools]   = useState([])
  const [cats, setCats]     = useState({})
  const [fired, setFired]   = useState(0)
  const [loading, setLoading] = useState(true)
  const [err, setErr]       = useState(null)

  useEffect(() => {
    setLoading(true)
    setErr(null)
    const url = runId ? `${API}/admin/tools?run_id=${runId}` : `${API}/admin/tools`
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => {
        setTools(Array.isArray(d.tools) ? d.tools : [])
        setCats(d.categories && typeof d.categories === 'object' ? d.categories : {})
        setFired(typeof d.fired_count === 'number' ? d.fired_count : 0)
        setLoading(false)
      })
      .catch(e => { setErr(e.message); setLoading(false) })
  }, [runId])

  if (loading) return <p className="text-slate-500 text-sm p-4">Loading tools…</p>
  if (err)     return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-sm text-red-400">
      ✗ Failed to load tools: {err}<br/>
      <span className="text-xs text-red-300/60">Make sure the backend is running and /admin/tools returns data.</span>
    </div>
  )
  if (!tools.length) return <p className="text-slate-500 text-sm p-4">No tools found.</p>

  const TCOLOR = { investigation: '#14b8a6', diagnosis: '#8b5cf6', fix: '#f59e0b', verify: '#22c55e' }

  // Group by category
  const groups = {}
  tools.forEach(t => {
    const c = t.category || 'other'
    if (!groups[c]) groups[c] = []
    groups[c].push(t)
  })

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="flex gap-6 bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div><div className="text-2xl font-semibold text-slate-100">{tools.length}</div><div className="text-xs text-slate-500">total tools</div></div>
        <div><div className="text-2xl font-semibold text-green-400">{fired}</div><div className="text-xs text-slate-500">fired this run</div></div>
        <div><div className="text-2xl font-semibold text-slate-500">{tools.length - fired}</div><div className="text-xs text-slate-500">not called</div></div>
        <div className="ml-auto flex flex-wrap gap-2 items-center">
          {Object.entries(TCOLOR).map(([k, c]) => (
            <span key={k} className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: c + '20', color: c, border: `1px solid ${c}40` }}>
              {cats[k]?.icon || ''} {cats[k]?.label || k}
            </span>
          ))}
        </div>
      </div>

      {/* Groups */}
      {Object.entries(groups).map(([cat, catTools]) => {
        const color   = TCOLOR[cat] || '#475569'
        const catMeta = cats[cat] || {}
        return (
          <div key={cat}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {catMeta.icon || ''} {catMeta.label || cat}
              </span>
              <span className="text-xs text-slate-600">({catTools.length})</span>
            </div>

            <div className="space-y-2">
              {catTools.map(tool => (
                <div key={tool.name}
                  className={`border rounded-xl overflow-hidden ${tool.fired ? 'border-slate-700 bg-slate-900' : 'border-slate-800/50 bg-slate-900/40'}`}>

                  {/* Header row */}
                  <div className="flex items-start gap-3 p-3">
                    <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${tool.fired ? 'bg-green-400' : 'bg-slate-700'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center flex-wrap gap-2 mb-1">
                        <code className="text-sm font-mono text-slate-200">{tool.name}</code>
                        {tool.fired
                          ? <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 border border-green-500/30">✓ fired</span>
                          : <span className="text-xs text-slate-600">not called</span>}
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed mb-2">{tool.description || ''}</p>
                      <div className="flex flex-wrap gap-1">
                        {(tool.params || []).map((p, i) => {
                          const label = typeof p === 'string' ? p : (p.name || JSON.stringify(p))
                          return <code key={i} className="text-xs bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">{label}</code>
                        })}
                      </div>
                    </div>
                    {tool.fired && tool.call_data?.duration_sec > 0 && (
                      <span className="text-xs text-slate-500 flex-shrink-0">{tool.call_data.duration_sec}s</span>
                    )}
                  </div>

                  {/* Call data */}
                  {tool.fired && tool.call_data && (
                    <div className="border-t border-slate-800 px-3 pb-3 pt-2 space-y-2">
                      {tool.call_data.node && (
                        <div className="text-xs text-slate-600">
                          Called by: <span className="text-slate-400 font-mono">{tool.call_data.node}</span>
                        </div>
                      )}
                      {tool.call_data.output && (
                        <Collapsible label="Output" defaultOpen right={
                          <CopyBtn text={JSON.stringify(tool.call_data.output, null, 2)} />
                        }>
                          <CodeBlock text={JSON.stringify(tool.call_data.output, null, 2)} maxH="220px" />
                        </Collapsible>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}


const SYSTEM_PROMPT_PREVIEW = `You are an expert platform engineering incident triage agent.
You investigate service alerts, determine root cause, and either resolve
the incident automatically or recommend actions to the on-call engineer.

DECISION RULES:
- Root cause clear + runbook risk=low + P2/P3 → auto_fix
- External AWS outage or third-party issue → needs_approval
- P1 severity → always needs_approval
- Root cause unclear → cannot_fix

See backend/agent/prompts.py → SYSTEM_PROMPT for the full version.`

function LLMInspectorTab({ runId }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!runId) return
    fetch(`${API}/admin/runs/${runId}/llm_calls`).then(r => r.json()).then(setData).catch(() => {})
  }, [runId])

  if (!runId) return <p className="text-slate-500 text-sm p-4">Select a run to inspect LLM calls.</p>
  if (!data)  return <p className="text-slate-500 text-sm p-4">Loading LLM calls…</p>

  const total_time = data.llm_calls.reduce((s, c) => s + c.duration_sec, 0)

  return (
    <div className="space-y-4">
      {/* Header stats */}
      <div className="flex gap-6 bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div>
          <div className="text-2xl font-semibold text-slate-100">{data?.total || 0}</div>
          <div className="text-xs text-slate-500">LLM calls</div>
        </div>
        <div>
          <div className="text-2xl font-semibold text-purple-400">{total_time.toFixed(1)}s</div>
          <div className="text-xs text-slate-500">total LLM time</div>
        </div>
        <div className="ml-auto text-xs text-slate-600 self-center">
          Model: <span className="text-slate-400">qwen3:14b via Ollama</span>
        </div>
      </div>

      {/* System prompt (shared across all calls) */}
      <Collapsible label="System prompt (shared across all calls)">
        <CodeBlock text={SYSTEM_PROMPT_PREVIEW} maxH="300px" />
        <div className="px-3 pb-2 text-xs text-slate-600 italic">
          Full prompt in backend/agent/prompts.py → SYSTEM_PROMPT
        </div>
      </Collapsible>

      {/* Per-node LLM calls */}
      {(data?.llm_calls?.length ?? 0) === 0 ? (
        <div className="text-slate-500 text-sm p-4 bg-slate-900 border border-slate-800 rounded-xl">
          No LLM calls recorded yet. Run a new investigation — prompts are stored from next run onwards.
        </div>
      ) : (
        (data?.llm_calls || []).map((call, i) => (
          <div key={i} className="border border-slate-700 rounded-xl overflow-hidden bg-slate-900">
            {/* Call header */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-800">
              <div className="w-2 h-2 rounded-full bg-purple-500" />
              <code className="text-sm font-mono text-slate-200">{call.node_name}</code>
              <Badge label="LLM call" color="#8b5cf6" />
              <span className="ml-auto text-xs text-slate-500">{call.duration_sec}s</span>
              {call.status === 'complete'
                ? <span className="text-xs text-green-400">✓</span>
                : <span className="text-xs text-blue-400">●</span>}
            </div>

            <div className="p-3 space-y-2">
              {/* Prompt */}
              <Collapsible
                label="Prompt sent to LLM"
                right={call.llm_prompt ? <CopyBtn text={call.llm_prompt} /> : null}>
                {call.llm_prompt
                  ? <CodeBlock text={call.llm_prompt} maxH="300px" />
                  : <div className="p-3 text-xs text-slate-600 italic">
                      Prompt not stored — start a new run to capture prompts
                    </div>}
              </Collapsible>

              {/* Response */}
              <Collapsible
                label="LLM response"
                defaultOpen
                right={call.llm_response ? <CopyBtn text={call.llm_response} /> : null}>
                {call.llm_response
                  ? <CodeBlock text={call.llm_response} maxH="300px" />
                  : <div className="p-3 text-xs text-slate-600 italic">No response stored</div>}
              </Collapsible>
            </div>
          </div>
        ))
      )}
    </div>
  )
}

// ── Timeline tab ──────────────────────────────────────────────────────────────
function TimelineTab({ runId }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!runId) return
    fetch(`${API}/admin/runs/${runId}/timeline`).then(r => r.json()).then(setData).catch(() => {})
  }, [runId])

  if (!runId) return <p className="text-slate-500 text-sm p-4">Select a run to view its timeline.</p>
  if (!data)  return <p className="text-slate-500 text-sm p-4">Loading timeline…</p>

  const maxDur = Math.max(...data.timeline.map(s => s.duration_sec), 1)

  return (
    <div className="space-y-4">
      {/* Run summary */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <span className="font-semibold text-slate-100">{data?.service || ""}</span>
            <span className="text-slate-500 text-sm ml-2">· {data?.scenario || ""}</span>
          </div>
          <Badge
            label={data?.status || "unknown"}
            color={data.status === 'complete' ? '#22c55e' : data.status === 'failed' ? '#ef4444' : '#f59e0b'} />
        </div>
        <div className="text-xs text-slate-500">Total: {data.total_duration || 0}s · {(data.timeline || []).length} steps</div>
      </div>

      {/* Step-by-step timeline */}
      <div className="space-y-2">
        {(data.timeline || []).map((step, i) => {
          const color = CAT_COLOR[step.category] || '#475569'
          const barW  = Math.max((step.duration_sec / maxDur) * 100, step.duration_sec > 0 ? 2 : 0)
          const hasLLM  = step.llm_prompt || step.llm_response
          const hasTools = step.tool_output

          return (
            <div key={step.step_id || i}
              className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900">

              {/* Step header */}
              <div className="flex items-center gap-3 px-4 py-3">
                {/* Status icon */}
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs flex-shrink-0 ${
                  step.status === 'complete' ? 'bg-green-500/20 text-green-400' :
                  step.status === 'running'  ? 'bg-blue-500/20 text-blue-400' :
                                              'bg-red-500/20 text-red-400'
                }`}>
                  {step.status === 'complete' ? '✓' : step.status === 'running' ? '●' : '✗'}
                </div>

                <code className="text-sm font-mono text-slate-200">{step.node_name}</code>
                <Badge label={step.category} color={color} />

                {/* Duration bar */}
                <div className="flex-1 flex items-center gap-2 ml-2">
                  <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden">
                    <div className="h-full rounded" style={{ width: `${barW}%`, background: color }} />
                  </div>
                  <span className="text-xs text-slate-500 w-10 text-right flex-shrink-0">
                    {step.duration_sec > 0 ? `${step.duration_sec}s` : '< 0.1s'}
                  </span>
                </div>
              </div>

              {/* Reasoning preview */}
              {step.reasoning_preview && (
                <div className="px-4 pb-2">
                  <p className="text-xs text-slate-400 leading-relaxed line-clamp-2">
                    {step.reasoning_preview}
                  </p>
                </div>
              )}

              {/* Expandable details */}
              {(hasLLM || hasTools) && (
                <div className="border-t border-slate-800 px-3 pb-3 pt-2 space-y-2">
                  {hasLLM && (
                    <Collapsible
                      label="Prompt sent to LLM"
                      right={step.llm_prompt ? <CopyBtn text={step.llm_prompt} /> : null}>
                      <CodeBlock text={step.llm_prompt || '(not stored)'} maxH="250px" />
                    </Collapsible>
                  )}
                  {hasLLM && (
                    <Collapsible
                      label="LLM response"
                      defaultOpen={false}
                      right={step.llm_response ? <CopyBtn text={step.llm_response} /> : null}>
                      <CodeBlock text={step.llm_response || '(not stored)'} maxH="250px" />
                    </Collapsible>
                  )}
                  {hasTools && (
                    <Collapsible
                      label="Tool output"
                      defaultOpen
                      right={<CopyBtn text={JSON.stringify(step.tool_output, null, 2)} />}>
                      <CodeBlock text={JSON.stringify(step.tool_output, null, 2)} maxH="280px" />
                    </Collapsible>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Final report */}
      {data?.final_report && (
        <div className="border border-green-500/30 bg-green-500/5 rounded-xl p-4">
          <div className="text-xs text-green-400 font-semibold uppercase tracking-wider mb-2">
            ✓ Final triage report
          </div>
          <pre className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed font-mono">
            {data?.final_report?.report || ""}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── Telemetry tab ─────────────────────────────────────────────────────────────
function TelemetryTab({ runId }) {
  const [tel, setTel] = useState(null)
  useEffect(() => {
    if (!runId) return
    fetch(`${API}/admin/runs/${runId}/telemetry`).then(r => r.json()).then(setTel).catch(() => {})
  }, [runId])

  if (!runId) return <p className="text-slate-500 text-sm p-4">Select a run.</p>
  if (!tel)   return <p className="text-slate-500 text-sm p-4">Loading…</p>

  const maxDur = Math.max(...tel.steps.map(s => s.duration_sec), 1)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: 'Total time',   value: `${tel.total_duration_sec}s`, color: '#e2e8f0' },
          { label: 'LLM time',     value: `${tel.total_llm_time_sec}s`, color: '#8b5cf6' },
          { label: 'LLM calls',    value: tel.llm_call_count,           color: '#8b5cf6' },
          { label: 'Tool calls',   value: tel.tool_call_count,          color: '#14b8a6' },
        ].map(m => (
          <div key={m.label} className="bg-slate-900 border border-slate-800 rounded-xl p-3">
            <div className="text-xs text-slate-500 mb-1">{m.label}</div>
            <div className="text-2xl font-semibold" style={{ color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Step waterfall</div>
        <div className="space-y-2">
          {tel.steps.map((s, i) => (
            <div key={i}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-slate-400 font-mono">{s.node_name}</span>
                <span className="text-slate-500">{s.duration_sec}s</span>
              </div>
              <div className="h-4 bg-slate-800 rounded overflow-hidden">
                <div className="h-full rounded" style={{
                  width: `${(s.duration_sec / maxDur) * 100}%`,
                  minWidth: s.duration_sec > 0 ? '4px' : '0',
                  background: CAT_COLOR[s.category] || '#475569',
                }} />
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-4 mt-3 pt-3 border-t border-slate-800">
          {Object.entries(CAT_COLOR).map(([k, c]) => (
            <div key={k} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />
              <span className="text-xs text-slate-500">{k}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main AdminDashboard ───────────────────────────────────────────────────────
export default function AdminDashboard({ onBack }) {
  const [systemInfo,     setSystemInfo]     = useState(null)
  const [graphData,      setGraphData]      = useState(null)
  const [runs,           setRuns]           = useState([])
  const [selectedRunId,  setSelectedRunId]  = useState(null)
  const [selectedRun,    setSelectedRun]    = useState(null)
  const [activeNode,     setActiveNode]     = useState(null)
  const [completedNodes, setCompletedNodes] = useState([])
  const [tab,            setTab]            = useState('graph')
  const wsRef  = useRef(null)
  const pollRef = useRef(null)

  // Initial load
  useEffect(() => {
    const load = async () => {
      try {
        const [sysR, graphR, runsR] = await Promise.all([
          fetch(`${API}/admin/system`),
          fetch(`${API}/admin/graph`),
          fetch(`${API}/api/runs`),
        ])
        setSystemInfo(await sysR.json())
        setGraphData(await graphR.json())
        const rd = await runsR.json()
        const allRuns = rd.runs || []
        setRuns(allRuns)
        const active = allRuns.find(r => r.status === 'running' || r.status === 'waiting_approval')
        if (active) setSelectedRunId(active.run_id)
        else if (allRuns[0]) setSelectedRunId(allRuns[0].run_id)
      } catch {}
    }
    load()
  }, [])

  // Auto-refresh system + runs list every 3s
  useEffect(() => {
    const i = setInterval(async () => {
      try {
        const [sysR, runsR] = await Promise.all([
          fetch(`${API}/admin/system`),
          fetch(`${API}/api/runs`),
        ])
        setSystemInfo(await sysR.json())
        const rd = await runsR.json()
        setRuns(rd.runs || [])
      } catch {}
    }, 3000)
    return () => clearInterval(i)
  }, [])

  // Auto-refresh active-run data (timeline/telemetry) every 3s while running
  useEffect(() => {
    if (!selectedRunId) return
    if (pollRef.current) clearInterval(pollRef.current)

    const refresh = async () => {
      try {
        const r = await fetch(`${API}/api/runs/${selectedRunId}`)
        const d = await r.json()
        setSelectedRun(d)
        if (['complete', 'failed', 'aborted'].includes(d.status)) {
          clearInterval(pollRef.current)
        }
      } catch {}
    }
    refresh()
    pollRef.current = setInterval(refresh, 3000)
    return () => clearInterval(pollRef.current)
  }, [selectedRunId])

  // WebSocket for live graph node tracking
  useEffect(() => {
    if (!selectedRunId) return
    if (wsRef.current) wsRef.current.close()
    setActiveNode(null)
    setCompletedNodes([])

    fetch(`${API}/api/runs/${selectedRunId}`)
      .then(r => r.json())
      .then(d => {
        setCompletedNodes((d.steps || []).filter(s => s.status === 'complete').map(s => s.node_name))
        const running = (d.steps || []).find(s => s.status === 'running')
        if (running) setActiveNode(running.node_name)
      }).catch(() => {})

    const ws = new WebSocket(`ws://localhost:8000/ws/${selectedRunId}`)
    wsRef.current = ws
    ws.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'step_start')    setActiveNode(msg.data.node_name)
      if (msg.type === 'step_complete') { setActiveNode(null); setCompletedNodes(p => [...new Set([...p, msg.data.node_name])]) }
      if (msg.type === 'complete' || msg.type === 'error') setActiveNode(null)
    }
    return () => ws.close()
  }, [selectedRunId])

  const TABS = [
    { id: 'graph',     label: '🗺️ Graph' },
    { id: 'system',    label: '⚙️ System' },
    { id: 'tools',     label: '🔧 Tools' },
    { id: 'llm',       label: '🤖 LLM Inspector' },
    { id: 'timeline',  label: '📋 Timeline' },
    { id: 'telemetry', label: '📊 Telemetry' },
  ]

  const activeRun = runs.find(r => r.run_id === selectedRunId)
  const isRunning = activeRun && ['running', 'waiting_approval'].includes(activeRun.status)

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-200">
      {/* Header */}
      <div className="flex items-center gap-4 px-5 py-3 border-b border-slate-800 bg-slate-900 flex-shrink-0">
        <button onClick={onBack} className="text-slate-500 hover:text-slate-200 text-sm transition-colors">
          ← Back
        </button>
        <div className="font-semibold text-slate-100">Admin — Behind the scenes</div>
        {isRunning && (
          <div className="flex items-center gap-1.5 text-xs text-blue-400">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-400 pulse" />
            live · refreshing every 3s
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs text-slate-500">Run:</span>
          <select value={selectedRunId || ''} onChange={e => setSelectedRunId(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 focus:outline-none max-w-xs">
            <option value="">— select —</option>
            {runs.map(r => (
              <option key={r.run_id} value={r.run_id}>
                {r.service} · {r.scenario} · {r.status}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 px-5 pt-3 border-b border-slate-800 flex-shrink-0 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm rounded-t whitespace-nowrap transition-colors ${
              tab === t.id
                ? 'bg-slate-800 text-slate-100 border border-b-0 border-slate-700'
                : 'text-slate-500 hover:text-slate-300'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {tab === 'graph'     && <GraphTab     graphData={graphData} activeNode={activeNode} completedNodes={completedNodes} />}
        {tab === 'system'    && <SystemTab    info={systemInfo} />}
        {tab === 'tools'     && <ToolsTab     runId={selectedRunId} />}
        {tab === 'llm'       && <LLMInspectorTab runId={selectedRunId} />}
        {tab === 'timeline'  && <TimelineTab  runId={selectedRunId} />}
        {tab === 'telemetry' && <TelemetryTab runId={selectedRunId} />}
      </div>
    </div>
  )
}