import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CircuitModel, ComponentType } from './model'

export function useCatalog() {
  return useQuery({ queryKey: ['components'], queryFn: () => api.get<ComponentType[]>('/api/components'), staleTime: Infinity })
}

export function useCircuit(projectId: string, kind: string) {
  return useQuery({
    queryKey: ['circuit', projectId, kind],
    queryFn: () => api.get<{ kind: string; circuit: CircuitModel | null }>(`/api/projects/${projectId}/circuits/${kind}`),
  })
}
