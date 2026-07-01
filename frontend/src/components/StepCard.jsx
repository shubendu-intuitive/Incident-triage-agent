import { useState } from 'react'

const NODE_LABELS = {
  plan_investigation:         'Planning investigation',
  run_parallel_investigation: 'Running parallel checks',
  analyse_initial_findings:   'Analysing initial findings',
  deep_diagnosis:             'Running deep diagnosis',
  fetch_runbook:              'Fetching runbook',
  decide_action:              'Deciding on action',
  execute_fix:                'Executing fix',
  human_checkpoint:           'Human checkpoint',
  execute_approved_fix:       'Executing approved fix',
  cannot_fix:                 'Cannot fix — escalating',
  verify_outcome:             'Verifying outcome',
  generate_report:            'Generating report',
}

const NODE_ICONS = {
  plan_investigation:         '🔍',
  run_parallel_investigation: '⚡',
  analyse_initial_findings:   '🧠',
  deep_diagnosis:             '🔬',
  fetch_runbook:              '📋',
  decide_action:              '⚖️',
  execute_fix:                '🔧',
  human_checkpoint:           '👤',
  execute_approved_fix:       '🔧',
  cannot_fix:                 '⚠️',
  verify_outcome:             '✅',
  generate_report:            '📄',
}

function StatusIcon({ status }) {
  if (status === 'running') {
    return (
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full spinner" />
    )
  }
  if (status === 'complete') {
    return <div className="w-5 h-5 bg-green-500/20 rounded-full flex items-center justify-center text-green-400 text-xs">✓</div>
  }
  if (status === 'failed') {
    return <div className="w-5 h-5 bg-red-500/20 rounded-full flex items-center justify-center text-red-400 text-xs">✗</div>
  }
  return <div className="w-5 h-5 bg-slate-700 rounded-full" />
}

export default function StepCard({ step }) {
  const [expanded, setExpanded] = useState(false)

  const label = NODE_LABELS[step.node_name] || step.node_name
  const icon = NODE_ICONS[step.node_name] || '•'
  const hasOutput = step.tool_output && Object.keys(step.tool_output).length > 0

  return (
    <div className={`border rounded-lg overflow-hidden transition-all ${
      step.status === 'running'
        ? 'border-blue-500/50 bg-blue-500/5'
        : 'border-slate-800 bg-slate-900/50'
    }`}>
      {/* Step header */}
      <div className="flex items-start gap-3 p-3">
        <StatusIcon status={step.status} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm">{icon}</span>
            <span className="text-slate-300 text-sm font-medium">{label}</span>
            {step.node_name === 'run_parallel_investigation' && (
              <span className="text-xs text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">parallel</span>
            )}
          </div>

          {/* Agent reasoning — always visible, this is the "wow" part */}
          {step.agent_reasoning && (
            <p className="text-slate-400 text-xs leading-relaxed">
              {step.agent_reasoning}
            </p>
          )}

          {/* Tool output toggle */}
          {hasOutput && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 text-xs text-slate-500 hover:text-slate-400 flex items-center gap-1"
            >
              <span>{expanded ? '▾' : '▸'}</span>
              <span>Tool output</span>
            </button>
          )}
        </div>

        {/* Duration */}
        {step.completed_at && step.started_at && (
          <span className="text-slate-600 text-xs whitespace-nowrap">
            {Math.round((new Date(step.completed_at) - new Date(step.started_at)) / 100) / 10}s
          </span>
        )}
      </div>

      {/* Expandable tool output */}
      {expanded && hasOutput && (
        <div className="border-t border-slate-800 p-3 bg-slate-950/50">
          <pre className="text-xs text-slate-400 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(step.tool_output, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
