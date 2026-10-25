import { useState } from 'react'
import { Link, NavLink, Route, Routes, useParams } from 'react-router-dom'
import { useExperiments, useProject, useUpdateProject } from '../api/hooks'
import type { Project } from '../api/types'
import { ErrorBox } from '../components/ErrorBox'
import GuidePanel from '../components/GuidePanel'
import ReportsPanel from '../components/ReportsPanel'
import StudiesPanel from '../components/StudiesPanel'
import ScriptPanel from '../components/ScriptPanel'
import SpecForm from '../components/SpecForm'
import { t } from '../i18n'

function ProjectMetaForm({ project }: { project: Project }) {
  const update = useUpdateProject(project.id)
  const [notes, setNotes] = useState(project.notes)
  const [name, setName] = useState(project.name)
  return (
    <details className="card project-meta">
      <summary>פרטי הפרויקט: שם והערות על המערך הפיזי</summary>
      <div className="row">
        <label className="field grow">
          {t('project.rename')}
          <input className="input" name="rename" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field grow">
          {t('project.notes')}
          <input className="input" name="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button
          className="btn primary"
          style={{ alignSelf: 'end' }}
          disabled={update.isPending || !name.trim()}
          onClick={() => update.mutate({ name: name.trim(), notes })}
        >
          {t('project.save')}
        </button>
        {update.isSuccess && <span className="badge ok">{t('project.saved')}</span>}
      </div>
      {update.isError && <ErrorBox error={update.error} />}
    </details>
  )
}

export default function ProjectPage() {
  const { projectId = '' } = useParams()
  const project = useProject(projectId)
  const experiments = useExperiments()

  if (project.isLoading) return <p className="muted">{t('common.loading')}</p>
  if (project.isError) return <ErrorBox error={project.error} onRetry={() => void project.refetch()} />
  const p = project.data!
  const experiment = experiments.data?.find((x) => x.id === p.experiment_id)

  return (
    <div className="stack">
      <div className="page-head">
        <Link to="/" className="crumb">
          {t('project.back')}
        </Link>
      </div>
      <div className="page-head">
        <div className="grow">
          <h1 data-testid="project-title">{p.name}</h1>
          {experiment && (
            <div className="muted small" data-testid="project-experiment">
              {experiment.title_he}
            </div>
          )}
        </div>
        <a className="btn small" href={`/api/projects/${p.id}/export`} download={`project-${p.id.slice(0, 8)}.json`} data-testid="export">
          ייצוא גיבוי
        </a>
        <span className={`badge ${p.spec.provenance === 'assumed' ? 'assumed' : 'ok'}`}>
          {t(`provenance.${p.spec.provenance}`)}
        </span>
      </div>
      <ProjectMetaForm key={p.id} project={p} />
      <nav className="tabs" aria-label="project sections">
        <NavLink end to={`/projects/${p.id}`} className="tab">
          {t('tabs.studies')}
        </NavLink>
        <NavLink to={`/projects/${p.id}/guide`} className="tab">
          מצב מודרך
        </NavLink>
        <NavLink to={`/projects/${p.id}/spec`} className="tab">
          {experiment ? `מפרט ${experiment.equipment_he}` : t('tabs.spec')}
        </NavLink>
        <NavLink to={`/projects/${p.id}/script`} className="tab">
          סקריפט
        </NavLink>
        <NavLink to={`/projects/${p.id}/reports`} className="tab">
          דו״חות
        </NavLink>
      </nav>
      <Routes>
        <Route index element={<StudiesPanel projectId={p.id} />} />
        <Route path="guide" element={<GuidePanel projectId={p.id} />} />
        <Route path="reports" element={<ReportsPanel projectId={p.id} />} />
        <Route path="spec" element={<SpecForm key={p.id} project={p} />} />
        <Route path="script" element={<ScriptPanel key={p.id} projectId={p.id} experimentId={p.experiment_id} />} />
      </Routes>
    </div>
  )
}
