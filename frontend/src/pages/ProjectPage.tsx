import { useState } from 'react'
import { Link, NavLink, Route, Routes, useParams } from 'react-router-dom'
import { useProject, useUpdateProject } from '../api/hooks'
import type { Project } from '../api/types'
import { ErrorBox } from '../components/ErrorBox'
import StudiesPanel from '../components/StudiesPanel'
import TransformerForm from '../components/TransformerForm'
import { t } from '../i18n'

function ProjectMetaForm({ project }: { project: Project }) {
  const update = useUpdateProject(project.id)
  const [notes, setNotes] = useState(project.notes)
  const [name, setName] = useState(project.name)
  return (
    <section className="card stack">
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
    </section>
  )
}

export default function ProjectPage() {
  const { projectId = '' } = useParams()
  const project = useProject(projectId)

  if (project.isLoading) return <p className="muted">{t('common.loading')}</p>
  if (project.isError) return <ErrorBox error={project.error} onRetry={() => void project.refetch()} />
  const p = project.data!

  return (
    <div className="stack">
      <div className="row">
        <Link to="/" className="small">
          → {t('project.back')}
        </Link>
      </div>
      <div className="row">
        <h1 className="grow" data-testid="project-title">
          {p.name}
        </h1>
        <span className={`badge ${p.transformer.provenance === 'assumed' ? 'assumed' : 'ok'}`}>
          {t(`provenance.${p.transformer.provenance}`)}
        </span>
      </div>
      <ProjectMetaForm key={p.id} project={p} />
      <nav className="tabs" aria-label="project sections">
        <NavLink end to={`/projects/${p.id}`} className="tab">
          {t('tabs.studies')}
        </NavLink>
        <NavLink to={`/projects/${p.id}/spec`} className="tab">
          {t('tabs.spec')}
        </NavLink>
      </nav>
      <Routes>
        <Route index element={<StudiesPanel projectId={p.id} />} />
        <Route path="spec" element={<TransformerForm key={p.id} project={p} />} />
      </Routes>
    </div>
  )
}
