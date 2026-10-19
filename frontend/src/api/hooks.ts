import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Comparison, Experiment, MSet, MSetView, Project, Reproduction, Run, RunSummary, Study } from './types'

export const keys = {
  experiments: ['experiments'] as const,
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
}

export function useExperiments() {
  return useQuery({ queryKey: keys.experiments, queryFn: () => api.get<Experiment[]>('/api/experiments') })
}

export function useProjects() {
  return useQuery({ queryKey: keys.projects, queryFn: () => api.get<Project[]>('/api/projects') })
}

export function useProject(id: string) {
  return useQuery({ queryKey: keys.project(id), queryFn: () => api.get<Project>(`/api/projects/${id}`) })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; experiment_id: string }) => api.post<Project>('/api/projects', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  })
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Pick<Project, 'name' | 'notes' | 'spec'>>) =>
      api.patch<Project>(`/api/projects/${id}`, body),
    onSuccess: (p) => {
      qc.setQueryData(keys.project(id), p)
      void qc.invalidateQueries({ queryKey: keys.projects })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/projects/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  })
}

export const runKeys = {
  studies: (pid: string) => ['studies', pid] as const,
  runs: (pid: string, kind?: string) => ['runs', pid, kind ?? 'all'] as const,
  run: (rid: string) => ['run', rid] as const,
}

export function useStudies(pid: string) {
  return useQuery({ queryKey: runKeys.studies(pid), queryFn: () => api.get<Study[]>(`/api/projects/${pid}/studies`) })
}

export function useRuns(pid: string, kind?: string) {
  return useQuery({
    queryKey: runKeys.runs(pid, kind),
    queryFn: () => api.get<RunSummary[]>(`/api/projects/${pid}/runs${kind ? `?study_kind=${kind}` : ''}`),
  })
}

export function useRun(rid: string | null) {
  return useQuery({
    queryKey: runKeys.run(rid ?? ''),
    queryFn: () => api.get<Run>(`/api/runs/${rid}`),
    enabled: !!rid,
  })
}

export function useCreateRun(pid: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { study_kind: string; case: Record<string, unknown>; label?: string }) =>
      api.post<Run>(`/api/projects/${pid}/runs`, body),
    onSuccess: (run) => {
      qc.setQueryData(runKeys.run(run.id), run)
      void qc.invalidateQueries({ queryKey: ['runs', pid] })
    },
  })
}

export function useReproduce() {
  return useMutation({ mutationFn: (rid: string) => api.post<Reproduction>(`/api/runs/${rid}/reproduce`) })
}

export const mKeys = {
  sets: (pid: string, kind: string) => ['msets', pid, kind] as const,
  set: (sid: string) => ['mset', sid] as const,
  cmp: (rid: string, sid: string, ref: string) => ['cmp', rid, sid, ref] as const,
}

export function useMeasurementSets(pid: string, kind: string) {
  return useQuery({
    queryKey: mKeys.sets(pid, kind),
    queryFn: () => api.get<MSet[]>(`/api/projects/${pid}/measurement-sets?study_kind=${kind}`),
  })
}

export function useMeasurementSet(sid: string | null) {
  return useQuery({
    queryKey: mKeys.set(sid ?? ''),
    queryFn: () => api.get<MSetView>(`/api/measurement-sets/${sid}`),
    enabled: !!sid,
  })
}

export function useComparison(rid: string | null, sid: string | null, reference: string) {
  return useQuery({
    queryKey: mKeys.cmp(rid ?? '', sid ?? '', reference),
    queryFn: () => api.get<Comparison>(`/api/comparison?run_id=${rid}&set_id=${sid}&reference=${reference}`),
    enabled: !!rid && !!sid,
  })
}
