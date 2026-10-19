import { Link, Route, Routes } from 'react-router-dom'
import { t } from './i18n'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'

export default function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          <img src="/favicon.svg" width={26} height={26} alt="" />
          <span>{t('app.title')}</span>
          <small>{t('app.subtitle')}</small>
        </Link>
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
