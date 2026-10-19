/**
 * Minimal i18n layer. Hebrew is the default; every UI string goes through t() so an English
 * dictionary can be added without touching components.
 */
import { he, type MessageKey } from './he'

const dictionaries: Record<string, Partial<Record<MessageKey, string>>> = { he }
let current = 'he'

export function setLocale(locale: string): void {
  if (dictionaries[locale]) current = locale
}

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const raw = dictionaries[current]?.[key] ?? he[key] ?? key
  if (!vars) return raw
  return raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`))
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('he-IL', { dateStyle: 'short', timeStyle: 'short' })
}
