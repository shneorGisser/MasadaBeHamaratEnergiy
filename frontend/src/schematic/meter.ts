/** Next standard lab-meter range (1 – 1.5 – 2.5 – 3 – 5 – 6 – 7.5 × 10ⁿ) above |v|, with 5 % headroom. */
const STEPS = [1, 1.5, 2.5, 3, 5, 6, 7.5, 10]

export function meterRange(v: number): number {
  const a = Math.abs(v) * 1.05
  if (!(a > 0)) return 1
  const p = Math.floor(Math.log10(a))
  for (const s of STEPS) if (s * 10 ** p >= a * (1 - 1e-12)) return +(s * 10 ** p).toPrecision(6)
  return 10 ** (p + 1)
}
