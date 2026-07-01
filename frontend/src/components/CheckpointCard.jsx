import { useState } from 'react'

export default function CheckpointCard({ checkpoint, runId, onResolved }) {
  const [selected, setSelected] = useState(checkpoint.recommendation || 'A')
  const [loading, setLoading] = useState(false)
  const [rejected, setRejected] = useState(false)

  const handleApprove = async () => {
    setLoading(true)
    try {
      await fetch(`http://localhost:8000/api/runs/${runId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          checkpoint_id: checkpoint.checkpoint_id,
          option_selected: selected,
        }),
      })
      onResolved()
    } catch (e) {
      alert('Failed to approve. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  const handleReject = async () => {
    setRejected(true)
    await fetch(`http://localhost:8000/api/runs/${runId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        checkpoint_id: checkpoint.checkpoint_id,
        reason: 'Operator rejected',
      }),
    })
    onResolved()
  }

  return (
    <div className="border-2 border-yellow-500/40 rounded-lg overflow-hidden bg-yellow-500/5">
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b border-yellow-500/20">
        <span className="text-lg">⏸</span>
        <div>
          <div className="text-yellow-400 text-sm font-semibold">Waiting for your approval</div>
          <div className="text-slate-400 text-xs">{checkpoint.question}</div>
        </div>
      </div>

      {/* Options */}
      <div className="p-3 space-y-2">
        {checkpoint.options.map(option => {
          const isRecommended = option.id === checkpoint.recommendation
          const isSelected = option.id === selected

          return (
            <button
              key={option.id}
              onClick={() => setSelected(option.id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                isSelected
                  ? 'border-blue-500/60 bg-blue-500/10'
                  : 'border-slate-700 hover:border-slate-600 bg-slate-900/50'
              }`}
            >
              <div className="flex items-start gap-2">
                <span className={`text-xs font-bold mt-0.5 w-5 h-5 rounded flex items-center justify-center ${
                  isSelected ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'
                }`}>
                  {option.id}
                </span>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-200 text-sm font-medium">{option.title}</span>
                    {isRecommended && (
                      <span className="text-xs bg-green-500/20 text-green-400 border border-green-500/30 px-1.5 py-0.5 rounded-full">
                        agent recommends
                      </span>
                    )}
                  </div>
                  <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">{option.description}</p>
                  <div className="flex items-center gap-3 mt-1">
                    {option.risk && (
                      <span className={`text-xs ${
                        option.risk === 'high'   ? 'text-red-400' :
                        option.risk === 'medium' ? 'text-yellow-400' :
                                                   'text-green-400'
                      }`}>
                        Risk: {option.risk}
                      </span>
                    )}
                    {option.cost && (
                      <span className="text-xs text-slate-500">Cost: {option.cost}</span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Actions */}
      <div className="flex gap-2 p-3 pt-0">
        <button
          onClick={handleApprove}
          disabled={loading}
          className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {loading ? 'Executing…' : `Approve option ${selected} →`}
        </button>
        <button
          onClick={handleReject}
          disabled={loading || rejected}
          className="px-4 py-2 border border-slate-700 hover:border-red-500/50 hover:text-red-400 text-slate-400 text-sm rounded-lg transition-colors"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
