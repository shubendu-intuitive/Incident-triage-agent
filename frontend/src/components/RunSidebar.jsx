import { useEffect, useState } from 'react'

const STATUS_STYLES = {
  running:          'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  waiting_approval: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  complete:         'bg-green-500/20 text-green-400 border border-green-500/30',
  failed:           'bg-red-500/20 text-red-400 border border-red-500/30',
  aborted:          'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  pending:          'bg-slate-500/20 text-slate-400 border border-slate-500/30',
}

const SEVERITY_DOT = {
  P1: 'bg-red-500',
  P2: 'bg-yellow-500',
  P3: 'bg-blue-500',
}

const STATUS_LABEL = {
  running:          '● running',
  waiting_approval: '⏸ needs you',
  complete:         '✓ resolved',
  failed:           '✗ failed',
  aborted:          '— aborted',
  pending:          '… pending',
}

function timeAgo(isoString) {
  const seconds = Math.floor((Date.now() - new Date(isoString)) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

export default function RunSidebar({ activeRunId, onSelectRun, onNewRun, refreshTrigger }) {
  const [runs, setRuns] = useState([])

  const fetchRuns = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/runs')
      const data = await res.json()
      setRuns(data.runs || [])
    } catch (e) {
      // Backend not yet running — fail silently
    }
  }

  useEffect(() => {
    fetchRuns()
  }, [refreshTrigger])

  // Refresh sidebar every 5 seconds so status stays current
  useEffect(() => {
    const interval = setInterval(fetchRuns, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="w-64 min-w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-screen">
      {/* Header */}
      <div className="p-4 border-b border-slate-800">
        <div className="flex items-center gap-2 mb-3">
          {/* Simple logo mark */}
          <div className="w-6 h-6 rounded bg-blue-600 flex items-center justify-center text-xs font-bold">T</div>
          <span className="font-semibold text-slate-100 text-sm">Incident Triage</span>
        </div>
        <button
          onClick={onNewRun}
          className="w-full py-2 px-3 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg font-medium transition-colors"
        >
          + New investigation
        </button>
        <a
          href="/admin"
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full mt-2 py-1.5 px-3 border border-slate-700 hover:border-slate-600 text-slate-500 hover:text-slate-300 text-xs rounded-lg transition-colors text-center"
        >
          ⚙ Admin — behind the scenes ↗
        </a>
      </div>

      {/* Runs list */}
      <div className="flex-1 overflow-y-auto p-2">
        {runs.length === 0 ? (
          <p className="text-slate-500 text-xs text-center mt-8 px-4">
            No investigations yet. Start one above.
          </p>
        ) : (
          <div className="space-y-1">
            {runs.map(run => (
              <button
                key={run.run_id}
                onClick={() => onSelectRun(run.run_id)}
                className={`w-full text-left p-3 rounded-lg transition-colors ${
                  activeRunId === run.run_id
                    ? 'bg-slate-700'
                    : 'hover:bg-slate-800'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-slate-200 text-xs font-medium truncate mr-2">
                    {run.service}
                  </span>
                  <div className={`flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full whitespace-nowrap ${STATUS_STYLES[run.status] || STATUS_STYLES.pending}`}>
                    <span className={run.status === 'running' ? 'pulse' : ''}>{STATUS_LABEL[run.status] || run.status}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${SEVERITY_DOT[run.severity] || 'bg-slate-500'}`} />
                  <span className="text-slate-500 text-xs">{run.severity} · {run.alert_type}</span>
                  <span className="text-slate-600 text-xs ml-auto">{timeAgo(run.created_at)}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}