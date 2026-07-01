import { useEffect, useRef, useState } from 'react'
import StepCard from './StepCard'
import CheckpointCard from './CheckpointCard'
import FinalReport from './FinalReport'

const SEVERITY_STYLES = {
  P1: 'bg-red-500/20 text-red-400 border border-red-500/30',
  P2: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  P3: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
}

const RUN_STATUS_STYLES = {
  running:          'text-blue-400',
  waiting_approval: 'text-yellow-400',
  complete:         'text-green-400',
  failed:           'text-red-400',
  aborted:          'text-slate-400',
}

function ElapsedTimer({ startTime }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - new Date(startTime)) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [startTime])

  const m = Math.floor(elapsed / 60)
  const s = elapsed % 60
  return <span>{m > 0 ? `${m}m ` : ''}{s}s</span>
}

export default function RunFeed({ runId }) {
  const [run, setRun] = useState(null)
  const [steps, setSteps] = useState([])
  const [checkpoint, setCheckpoint] = useState(null)
  const [finalReport, setFinalReport] = useState(null)
  const [incidentStatus, setIncidentStatus] = useState(null)
  const [connected, setConnected] = useState(false)
  const [terminating, setTerminating] = useState(false)
  const wsRef = useRef(null)
  const bottomRef = useRef(null)

  // Load existing state when run is selected (for viewing past runs or reconnects)
  useEffect(() => {
    if (!runId) return

    const fetchRun = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/runs/${runId}`)
        const data = await res.json()
        setRun(data)
        setSteps(data.steps || [])
        setCheckpoint(data.checkpoint || null)
        if (data.final_report) {
          setFinalReport(data.final_report.report)
          setIncidentStatus(data.final_report.status)
        }
      } catch (e) {
        // Backend not ready yet
      }
    }

    fetchRun()

    // Poll every 2s while run is active — catches steps that fired before WS connected
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/runs/${runId}`)
        const data = await res.json()
        // Stop polling once terminal state reached
        if (['complete', 'failed', 'aborted'].includes(data.status)) {
          clearInterval(poll)
        }
        setRun(data)
        // Only update steps from REST if WS hasn't given us more
        setSteps(prev => {
          const wsIds = new Set(prev.map(s => s.step_id))
          const restSteps = data.steps || []
          // Merge: keep WS steps (may have richer data), add any REST steps not yet in state
          const merged = [...restSteps]
          prev.forEach(s => {
            if (!restSteps.find(r => r.step_id === s.step_id)) merged.push(s)
          })
          merged.sort((a, b) => new Date(a.started_at) - new Date(b.started_at))
          return merged
        })
        if (data.final_report && !finalReport) {
          setFinalReport(data.final_report.report)
          setIncidentStatus(data.final_report.status)
        }
        if (data.checkpoint && !checkpoint) {
          setCheckpoint(data.checkpoint)
        }
      } catch {}
    }, 2000)

    return () => clearInterval(poll)
  }, [runId])

  // WebSocket connection for live streaming
  useEffect(() => {
    if (!runId) return

    const ws = new WebSocket(`ws://localhost:8000/ws/${runId}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)

      if (msg.type === 'step_start') {
        // Add a new "running" step to the feed
        setSteps(prev => [...prev, {
          step_id: msg.data.step_id,
          node_name: msg.data.node_name,
          status: 'running',
          started_at: msg.data.timestamp,
          agent_reasoning: null,
          tool_output: null,
        }])
      }

      else if (msg.type === 'step_complete') {
        // Update the existing step with results
        setSteps(prev => prev.map(s =>
          s.step_id === msg.data.step_id
            ? {
                ...s,
                status: 'complete',
                completed_at: msg.data.timestamp,
                agent_reasoning: msg.data.reasoning,
                tool_output: msg.data.output,
              }
            : s
        ))
      }

      else if (msg.type === 'checkpoint') {
        setCheckpoint(msg.data)
        setRun(prev => prev ? { ...prev, status: 'waiting_approval' } : prev)
      }

      else if (msg.type === 'complete') {
        setFinalReport(msg.data.final_report)
        setIncidentStatus(msg.data.incident_status)
        setRun(prev => prev ? { ...prev, status: 'complete' } : prev)
        setCheckpoint(null)
      }

      else if (msg.type === 'error') {
        setRun(prev => prev ? { ...prev, status: 'failed' } : prev)
      }
    }

    return () => ws.close()
  }, [runId])

  // Auto-scroll to bottom as new steps appear
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps, checkpoint, finalReport])

  const handleTerminate = async () => {
    if (!window.confirm('Terminate this investigation? This cannot be undone.')) return
    setTerminating(true)
    try {
      await fetch(`http://localhost:8000/api/runs/${runId}/abort`, { method: 'POST' })
      setRun(prev => prev ? { ...prev, status: 'aborted' } : prev)
    } catch (e) {
      alert('Failed to terminate run')
    } finally {
      setTerminating(false)
    }
  }

  if (!runId) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
        Select a run from the sidebar or start a new investigation.
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
        Loading…
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      {/* Run header */}
      <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/80 flex items-center gap-3 flex-shrink-0">
        <span className="text-slate-100 font-semibold">{run.service}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEVERITY_STYLES[run.severity] || ''}`}>
          {run.severity}
        </span>
        <span className="text-slate-500 text-sm">{run.alert_type}</span>

        <div className="ml-auto flex items-center gap-4">
          {/* Elapsed timer */}
          <span className="text-slate-500 text-xs">
            <ElapsedTimer startTime={run.created_at} />
          </span>

          {/* Run status */}
          <span className={`text-xs font-medium ${RUN_STATUS_STYLES[run.status] || 'text-slate-400'}`}>
            {run.status === 'running'          ? '● investigating' :
             run.status === 'waiting_approval' ? '⏸ waiting for you' :
             run.status === 'complete'         ? '✓ complete' :
             run.status === 'failed'           ? '✗ failed' :
             run.status === 'aborted'          ? '— aborted' :
             run.status}
          </span>

          {/* WS indicator */}
          <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-500 pulse' : 'bg-slate-600'}`} title={connected ? 'Live' : 'Disconnected'} />

          {/* Terminate button — only show for active runs */}
          {(run.status === 'running' || run.status === 'waiting_approval') && (
            <button
              onClick={handleTerminate}
              disabled={terminating}
              className="px-2.5 py-1 text-xs border border-red-500/40 text-red-400 hover:bg-red-500/10 hover:border-red-500/70 rounded transition-colors disabled:opacity-50"
              title="Terminate investigation"
            >
              {terminating ? 'Stopping…' : '✕ Terminate'}
            </button>
          )}
        </div>
      </div>

      {/* Scenario badge */}
      <div className="px-5 py-2 bg-slate-950/50 border-b border-slate-800/50 flex-shrink-0">
        <span className="text-xs text-slate-600">Scenario: </span>
        <span className="text-xs text-slate-400 font-mono">{run.scenario}</span>
      </div>

      {/* Step feed */}
      <div className="flex-1 overflow-y-auto p-5 space-y-2">
        {steps.length === 0 && run.status === 'running' && (
          <div className="text-slate-500 text-sm flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full spinner" />
            Agent starting…
          </div>
        )}

        {steps.map(step => (
          <StepCard key={step.step_id} step={step} />
        ))}

        {/* HITL checkpoint */}
        {checkpoint && (
          <CheckpointCard
            checkpoint={checkpoint}
            runId={runId}
            onResolved={() => setCheckpoint(null)}
          />
        )}

        {/* Final report */}
        {finalReport && (
          <FinalReport report={finalReport} incidentStatus={incidentStatus} />
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}