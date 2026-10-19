import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useCreateProject, useDeleteProject, useExperiments, useProjects } from '../api/hooks'
import { ErrorBox } from '../components/ErrorBox'
import { fmtDate, t } from '../i18n'

export default function ProjectsPage() {
  const projects = useProjects()
  const experiments = useExperiments()
  const create = useCreateProject()
  const del = useDeleteProject()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [experimentId, setExperimentId] = useState('transformer3ph')

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    create.mutate(
      { name: name.trim(), experiment_id: experimentId },
      { onSuccess: (p) => navigate(`/projects/${p.id}`) },
    )
  }

  const titleOf = (id: string) => experiments.data?.find((x) => x.id === id)?.title_he ?? id

  return (
    <div className="stack">
      <h1>{t('projects.heading')}</h1>

      <form className="card row" onSubmit={onSubmit} aria-label={t('projects.new')}>
        <label className="field grow">
          {t('projects.name')}
          <input
            className="input"
            name="project-name"
            value={name}
            maxLength={200}
            placeholder={t('projects.namePlaceholder')}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          {t('projects.experiment')}
          <select
            className="input"
            name="experiment"
            value={experimentId}
            onChange={(e) => setExperimentId(e.target.value)}
          >
            {(experiments.data ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.title_he}
              </option>
            ))}
          </select>
        </label>
        <button className="btn primary" type="submit" disabled={!name.trim() || create.isPending} style={{ alignSelf: 'end' }}>
          {t('projects.create')}
        </button>
      </form>
      {create.isError && <ErrorBox error={create.error} />}

      <section className="card">
        {projects.isLoading && <p className="muted">{t('common.loading')}</p>}
        {projects.isError && <ErrorBox error={projects.error} onRetry={() => void projects.refetch()} />}
        {projects.data && projects.data.length === 0 && <p className="muted">{t('projects.empty')}</p>}
        {projects.data && projects.data.length > 0 && (
          <ul className="project-list" aria-label={t('projects.heading')}>
            {projects.data.map((p) => (
              <li key={p.id} className="project-item">
                <Link to={`/projects/${p.id}`}>{p.name}</Link>
                <span className="muted small">{titleOf(p.experiment_id)}</span>
                <span className="muted small grow">
                  {t('projects.updated')}: {fmtDate(p.updated_at)}
                </span>
                <button
                  className="btn small danger"
                  onClick={() => {
                    if (window.confirm(t('projects.confirmDelete', { name: p.name }))) del.mutate(p.id)
                  }}
                >
                  {t('projects.delete')}
                </button>
              </li>
            ))}
          </ul>
        )}
        {del.isError && <ErrorBox error={del.error} />}
      </section>
    </div>
  )
}
