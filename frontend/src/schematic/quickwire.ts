/** Terminal lookup for keyboard wiring (QuickWire.tsx). */
import type { CompNode } from './model'

export interface Terminal {
  key: string // "M.U1"
  component: string
  terminal: string
  label: string // component label, for the option text
}

export function terminalsOf(nodes: CompNode[]): Terminal[] {
  return nodes.flatMap((n) =>
    (n.data.ctype?.terminals ?? []).map((t) => ({
      key: `${n.id}.${t}`,
      component: n.id,
      terminal: t,
      label: n.data.comp.label || n.id,
    })),
  )
}

const norm = (s: string) => s.replace(/\s+/g, '').toLowerCase()

/** Find a terminal by what was typed: exact "comp.term" first, then a unique "term" alone. */
export function findTerminal(all: Terminal[], typed: string): Terminal | { error: string } {
  const q = norm(typed)
  if (!q) return { error: 'לא הוקלד הדק' }
  const exact = all.find((t) => norm(t.key) === q)
  if (exact) return exact
  const byName = all.filter((t) => norm(t.terminal) === q)
  if (byName.length === 1) return byName[0]!
  if (byName.length > 1) return { error: `"${typed}" קיים בכמה רכיבים: ${byName.map((t) => t.key).join(', ')} — כתבו רכיב.הדק` }
  return { error: `אין הדק "${typed}"` }
}
