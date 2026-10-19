import { ApiError } from '../api/client'
import { t } from '../i18n'

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'network') return t('errors.network')
    const details = Array.isArray(e.details)
      ? (e.details as { loc?: unknown[]; msg?: string }[])
          .map((d) => `${(d.loc ?? []).join('.')}: ${d.msg ?? ''}`)
          .join(' · ')
      : ''
    return details ? `${e.message} — ${details}` : e.message
  }
  return e instanceof Error ? e.message : String(e)
}
