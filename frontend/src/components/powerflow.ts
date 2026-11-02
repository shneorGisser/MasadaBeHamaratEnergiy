/** The power balance of an induction machine, read from the solver's internals. */

export interface Flow {
  P_in: number
  P_cu1: number
  P_fe: number
  P_ag: number
  P_cu2: number
  P_mech: number
  P_fw: number
  P2: number
  s: number
}

export function flowOf(internals: Record<string, Record<string, number>> | undefined, id: string): Flow | null {
  const tot = internals?.[`${id}.total`]
  const mech = internals?.[`${id}.mech`]
  if (!tot || !mech) return null
  const P_in = tot.P_cu1! + tot.P_fe! + tot.P_ag!
  return {
    P_in,
    P_cu1: tot.P_cu1!,
    P_fe: tot.P_fe!,
    P_ag: tot.P_ag!,
    P_cu2: tot.P_cu2!,
    P_mech: mech.P_mech!,
    P_fw: mech.P_fw!,
    P2: mech.P2!,
    s: mech.s!,
  }
}

/** Input minus everything that leaves: zero for a consistent balance (W). */
export function balanceResidual(f: Flow): number {
  return f.P_in - (f.P_cu1 + f.P_fe + f.P_cu2 + f.P_fw + f.P2)
}
