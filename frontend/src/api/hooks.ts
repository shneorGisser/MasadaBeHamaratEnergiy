import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Experiment, Project } from './types'

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
    mutationFn: (body: Partial<Pick<Project, 'name' | 'notes' | 'transformer'>>) =>
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
