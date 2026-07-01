import { useState } from 'react'
import RunSidebar from './components/RunSidebar'
import RunFeed from './components/RunFeed'
import NewRunForm from './components/NewRunForm'
import AdminDashboard from './admin/AdminDashboard'

// Check if we're on the /admin route
const IS_ADMIN = window.location.pathname === '/admin'

export default function App() {
  const [activeRunId,    setActiveRunId]    = useState(null)
  const [showNewRun,     setShowNewRun]     = useState(false)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // Render admin dashboard if on /admin path
  if (IS_ADMIN) {
    return <AdminDashboard onBack={() => window.location.href = '/'} />
  }

  const handleNewRun = (runId) => {
    setActiveRunId(runId)
    setShowNewRun(false)
    setRefreshTrigger(t => t + 1)
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <RunSidebar
        activeRunId={activeRunId}
        onSelectRun={(id) => { setActiveRunId(id); setShowNewRun(false) }}
        onNewRun={() => setShowNewRun(true)}
        refreshTrigger={refreshTrigger}
      />
      <main className="flex-1 overflow-hidden flex flex-col">
        {showNewRun ? (
          <NewRunForm
            onSubmit={handleNewRun}
            onCancel={() => setShowNewRun(false)}
          />
        ) : (
          <RunFeed runId={activeRunId} />
        )}
      </main>
    </div>
  )
}