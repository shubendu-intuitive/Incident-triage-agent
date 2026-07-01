const STATUS_CONFIG = {
  resolved:  { color: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/30',  label: '✓ Resolved' },
  mitigated: { color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', label: '⚡ Mitigated' },
  escalated: { color: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/30',    label: '⚠ Escalated' },
}

export default function FinalReport({ report, incidentStatus }) {
  const statusConfig = STATUS_CONFIG[incidentStatus] || STATUS_CONFIG.escalated

  // Parse the report text into sections
  const sections = {}
  if (report) {
    const lines = report.split('\n')
    let currentSection = null
    let currentContent = []

    for (const line of lines) {
      const match = line.match(/^(Root cause|Steps taken|Fix applied|Outcome|Watch for):\s*(.*)/)
      if (match) {
        if (currentSection) sections[currentSection] = currentContent.join('\n').trim()
        currentSection = match[1]
        currentContent = match[2] ? [match[2]] : []
      } else if (currentSection && line.trim()) {
        currentContent.push(line.trim())
      }
    }
    if (currentSection) sections[currentSection] = currentContent.join('\n').trim()
  }

  return (
    <div className={`border rounded-lg overflow-hidden ${statusConfig.border} ${statusConfig.bg}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-slate-800/50">
        <span className="text-slate-300 text-sm font-semibold">Triage report</span>
        <span className={`text-sm font-semibold ${statusConfig.color}`}>{statusConfig.label}</span>
      </div>

      <div className="p-4 space-y-3">
        {/* Root cause — prominent */}
        {sections['Root cause'] && (
          <div>
            <div className="text-slate-500 text-xs font-medium uppercase tracking-wide mb-1">Root cause</div>
            <p className="text-slate-100 text-sm font-medium">{sections['Root cause']}</p>
          </div>
        )}

        {/* Steps taken */}
        {sections['Steps taken'] && (
          <div>
            <div className="text-slate-500 text-xs font-medium uppercase tracking-wide mb-1">Steps taken</div>
            <div className="text-slate-300 text-xs leading-relaxed whitespace-pre-line">{sections['Steps taken']}</div>
          </div>
        )}

        {/* Fix applied + Outcome row */}
        <div className="grid grid-cols-2 gap-3">
          {sections['Fix applied'] && (
            <div>
              <div className="text-slate-500 text-xs font-medium uppercase tracking-wide mb-1">Fix applied</div>
              <p className="text-slate-300 text-xs">{sections['Fix applied']}</p>
            </div>
          )}
          {sections['Outcome'] && (
            <div>
              <div className="text-slate-500 text-xs font-medium uppercase tracking-wide mb-1">Outcome</div>
              <p className="text-slate-300 text-xs">{sections['Outcome']}</p>
            </div>
          )}
        </div>

        {/* Watch for */}
        {sections['Watch for'] && (
          <div className="border border-yellow-500/20 bg-yellow-500/5 rounded-lg p-2">
            <div className="text-yellow-400 text-xs font-medium mb-1">⚠ Watch for next 30 min</div>
            <p className="text-slate-300 text-xs">{sections['Watch for']}</p>
          </div>
        )}

        {/* Fallback: raw report if parsing failed */}
        {!sections['Root cause'] && report && (
          <pre className="text-slate-300 text-xs whitespace-pre-wrap leading-relaxed">{report}</pre>
        )}
      </div>
    </div>
  )
}
