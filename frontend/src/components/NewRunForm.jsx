import { useState } from 'react'

const SCENARIOS = [
  { value: 'auto_fix',             label: 'Auto fix — Lambda memory exhaustion (P2)', service: 'kb-ingestion-lambda',  alert_type: 'error_rate',   severity: 'P2' },
  { value: 'external_dependency',  label: 'External dep — Bedrock latency spike (P2)', service: 'amp-api-gateway',     alert_type: 'latency',      severity: 'P2' },
  { value: 'cascading_failure',    label: 'Cascading failure — DynamoDB + SQS (P1)',    service: 'workspace-api',       alert_type: 'error_rate',   severity: 'P1' },
]

export default function NewRunForm({ onSubmit, onCancel }) {
  const [scenario, setScenario]     = useState('auto_fix')
  const [service, setService]       = useState('kb-ingestion-lambda')
  const [alertType, setAlertType]   = useState('error_rate')
  const [severity, setSeverity]     = useState('P2')
  const [description, setDescription] = useState('')
  const [loading, setLoading]       = useState(false)

  // When scenario changes, auto-fill the other fields
  const handleScenarioChange = (val) => {
    setScenario(val)
    const preset = SCENARIOS.find(s => s.value === val)
    if (preset) {
      setService(preset.service)
      setAlertType(preset.alert_type)
      setSeverity(preset.severity)
    }
  }

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const res = await fetch('http://localhost:8000/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, alert_type: alertType, severity, description, scenario }),
      })
      const data = await res.json()
      onSubmit(data.run_id)
    } catch (e) {
      alert('Failed to start run. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-xl p-6">
        <h2 className="text-slate-100 font-semibold text-lg mb-1">New investigation</h2>
        <p className="text-slate-400 text-sm mb-6">Start an automated incident triage run.</p>

        <div className="space-y-4">
          {/* Scenario */}
          <div>
            <label className="text-slate-400 text-xs font-medium block mb-1">Demo scenario</label>
            <select
              value={scenario}
              onChange={e => handleScenarioChange(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:border-blue-500"
            >
              {SCENARIOS.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Service */}
          <div>
            <label className="text-slate-400 text-xs font-medium block mb-1">Service name</label>
            <input
              type="text"
              value={service}
              onChange={e => setService(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:border-blue-500"
              placeholder="e.g. kb-ingestion-lambda"
            />
          </div>

          {/* Alert type + severity row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-slate-400 text-xs font-medium block mb-1">Alert type</label>
              <select
                value={alertType}
                onChange={e => setAlertType(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="error_rate">error_rate</option>
                <option value="latency">latency</option>
                <option value="queue_backup">queue_backup</option>
                <option value="dependency_failure">dependency_failure</option>
              </select>
            </div>

            <div>
              <label className="text-slate-400 text-xs font-medium block mb-1">Severity</label>
              <select
                value={severity}
                onChange={e => setSeverity(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="P1">P1 — Critical</option>
                <option value="P2">P2 — High</option>
                <option value="P3">P3 — Medium</option>
              </select>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="text-slate-400 text-xs font-medium block mb-1">Description <span className="text-slate-600">(optional)</span></label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={2}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:border-blue-500 resize-none"
              placeholder="Any additional context about the alert..."
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-1">
            <button
              onClick={handleSubmit}
              disabled={loading || !service}
              className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {loading ? 'Starting…' : 'Start investigation →'}
            </button>
            <button
              onClick={onCancel}
              className="px-4 py-2.5 border border-slate-700 hover:border-slate-600 text-slate-400 text-sm rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
