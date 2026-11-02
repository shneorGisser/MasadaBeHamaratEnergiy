/** "Formula → numbers": put the recorded input values into a parameter's formula, so the
 * student sees exactly what was computed (and can redo it on a calculator). */
import { fmt } from '../format'

const BOUND = 'A-Za-z0-9_'

export function substitute(formula: string, inputs: Record<string, number> | undefined): string | null {
  if (!inputs) return null
  const keys = Object.keys(inputs).sort((a, b) => b.length - a.length) // U_k(I_n) before U_k
  if (!keys.length) return null
  let out = formula
  let used = 0
  // placeholders first, so a substituted number is never matched again by a shorter symbol
  const slots: string[] = []
  for (const k of keys) {
    const esc = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const re = new RegExp(`(?<![${BOUND}])${esc}(?![${BOUND}])`, 'g')
    if (!re.test(out)) continue
    out = out.replace(re, () => {
      slots.push(fmt(inputs[k], 4))
      return `\uE000${slots.length - 1}\uE000`
    })
    used++
  }
  if (!used) return null
  // negative and e-notation numbers get parentheses: 3·(−2)², (4.155e-4)², not 4.155e-4²
  return out.replace(/\uE000(\d+)\uE000/g, (_m, i: string) => {
    const v = slots[Number(i)]!
    return v.startsWith('-') || v.includes('e') ? `(${v})` : v
  })
}
