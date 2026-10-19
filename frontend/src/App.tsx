import { useQuery } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router-dom'
import { api } from './api/client'
import { t } from './i18n'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'

/** Server status lamp: green only when /api/health actually answers. */
function ServerLamp() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<{ status: string; version: string }>('/api/health'),
    refetchInterval: 15000,
    retry: false,
  })
  const state = health.isSuccess ? 'on' : health.isError ? 'off' : ''
  const label = health.isSuccess ? `שרת הסימולציה מחובר · גרסה ${health.data.version}` : health.isError ? 'שרת הסימולציה אינו זמין' : 'בודק חיבור לשרת…'
  return (
    <div className="panel-plate" title={label} data-testid="server-lamp" data-state={state || 'pending'}>
      <span className={`lamp ${state}`} aria-hidden />
      <span>{health.isSuccess ? 'שרת מחובר' : health.isError ? 'שרת לא זמין' : 'בודק…'}</span>
    </div>
  )
}

export default function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          <img src="/favicon.svg" width={28} height={28} alt="" />
          <span>{t('app.title')}</span>
          <small>{t('app.subtitle')}</small>
        </Link>
        <ServerLamp />
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:projectId/*" element={<ProjectPage />} />
        </Routes>
      </main>
    </>
  )
}
