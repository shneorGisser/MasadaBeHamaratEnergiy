/** Engineering number formatting. null/undefined → em dash (never 0 or NaN). */
export function fmt(v: unknown, sig = 4): string {
  if (v === null || v === undefined) return '—'
  if (typeof v !== 'number') return String(v)
  if (!Number.isFinite(v)) return '—'
  if (v === 0) return '0'
  const a = Math.abs(v)
  if (a >= 1e6 || a < 1e-3) return v.toExponential(sig - 1)
  const digits = Math.max(0, sig - 1 - Math.floor(Math.log10(a)))
  return v.toFixed(Math.min(digits, 6))
}

export function parseList(text: string): number[] | null {
  const parts = text
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean)
  if (parts.length === 0) return null
  const nums = parts.map(Number)
  return nums.every((n) => Number.isFinite(n)) ? nums : null
}

const LTR_RUN = /([A-Za-z0-9(√][A-Za-z0-9_.,=+\-·/()°%Ω√²′↔–:φ ]*[A-Za-z0-9)°%Ω²′φ]|[A-Za-z0-9])/g

/** Wrap Latin and number runs of a Hebrew sentence in Unicode isolates (LRI…PDI), so
 * "(Ip ↔ In)" or "L1–L2" keep their left-to-right order inside right-to-left text. */
export function iso(s: string): string {
  return s.replace(LTR_RUN, (m) => `⁦${m}⁩`)
}
