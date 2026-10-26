/**
 * Power-electronics bench: the converters of the lab's Appli-com racks, simulated in the
 * browser by ngspice (eecircuit-engine, MIT — ngspice compiled to WebAssembly).
 *
 * Why ngspice here and not our own MNA: the machines need phasors and saturation, which our
 * solver does; converters need switching, i.e. a time-domain SPICE with diodes and switches.
 * Every topology carries its textbook theory, and the bench shows theory next to simulation
 * with the deviation, so a result that disagrees is visible, never silently accepted.
 *
 * Component models (stated, not hidden):
 * - "ideal": diode with ≈ 0.04 V forward drop, switch R_on = 1 mΩ — what the formulas assume;
 * - "real": silicon diode (≈ 0.8–1 V at 1 A), switch R_on = 50 mΩ — closer to the rack.
 * - Rectifier diodes and thyristors have an R-C snubber (100 Ω, 0.1 µF), as on the rack.
 * - A thyristor is a gated switch in series with a diode. The firing unit holds its gate for
 *   the whole conduction interval (a "long pulse"), so latching and holding current do not
 *   arise; turn-off is natural (current reversal). This is what the formulas assume too.
 */

export type Mode = 'ideal' | 'real'

export interface Param {
  key: string
  label: string
  unit: string
  min: number
  max: number
  step: number
  def: number
}

export type P = Record<string, number>

/** A waveform to plot: an ngspice vector, or the difference of two node voltages. */
export interface Probe {
  key: string
  label: string
  unit: string
  /** vector name, e.g. 'v(out)' or 'i(vload)'; for a difference, two node voltages */
  expr: string | [string, string]
  /** shown on the first chart (outputs) or the second (inputs / switch) */
  chart: 0 | 1
}

export interface Check {
  key: string
  label: string
  unit: string
  sim: number
  theory: number | null
  formula: string
  /** relative tolerance for "agrees"; null = indicative only (theory for an idealised case) */
  tol: number | null
  note?: string
}

export interface Signals {
  /** samples of a probe inside the analysis window */
  get(key: string): [number, number][]
  window: [number, number]
  stats(key: string): { mean: number; rms: number; min: number; max: number; pp: number }
  /** RMS of harmonic n (1 = fundamental) over whole periods of f0, and THD */
  harmonic(key: string, f0: number, n: number): number
  thd(key: string, f0: number): number | null
}

export interface Topology {
  id: string
  title: string
  rack: string
  summary: string
  physics: string[]
  params: Param[]
  probes: Probe[]
  netlist(p: P, mode: Mode): string
  /** [t_stop, analysis window start, analysis window end, max step] */
  timing(p: P): { tstop: number; t0: number; t1: number; tmax: number }
  checks(p: P, s: Signals): Check[]
}

const SQ2 = Math.SQRT2
const SQ3 = Math.sqrt(3)
const DEG = Math.PI / 180

function models(mode: Mode): string {
  return mode === 'ideal'
    ? `.model DMOD D(Is=1e-12 N=0.05 Rs=1m)
.model SWM SW(Ron=1m Roff=1e8 Vt=5 Vh=0.5)`
    : `.model DMOD D(Is=2.5n N=1.75 Rs=30m Cjo=50p)
.model SWM SW(Ron=50m Roff=1e8 Vt=5 Vh=0.5)`
}

// Each thyristor and rectifier diode carries an R-C snubber, as the rack's modules do (the
// R-C drawn across the device on the panel). Without it, the source inductance would have its
// current cut instantly at turn-off, which no real circuit does and SPICE cannot integrate.
const SCR = `.subckt SCR a k g
S1 a x g 0 SWM
D1 x k DMOD
RSN a sn 100
CSN sn k 0.1u
.ends
.subckt DIO a k
D1 a k DMOD
RSN a sn 100
CSN sn k 0.1u
.ends`

/** A gate pulse train: on from angle `fromDeg` for `widthDeg`, every period of f [Hz]. */
function gate(name: string, node: string, f: number, fromDeg: number, widthDeg: number): string {
  const T = 1 / f
  const td = ((((fromDeg % 360) + 360) % 360) / 360) * T
  const pw = (widthDeg / 360) * T
  return `${name} ${node} 0 PULSE(0 10 ${td.toExponential(6)} 1n 1n ${pw.toExponential(6)} ${T.toExponential(6)})`
}

// Long gate pulses. Each thyristor conducts 120° (B6) or 180° (B2), but the pulse is held 30°
// (resp. 10°) longer: with source inductance the outgoing device must keep its gate through the
// commutation overlap, until its current has fallen to zero. In those extra degrees it is
// reverse biased, so it cannot fire again.
const GATE_B6 = 150
const GATE_B2 = 190

const OPTIONS = '.options reltol=1e-4 abstol=1e-9 vntol=1e-6 itl4=200'

/* ------------------------------------------------------------------ rectifiers */

const continuous = (s: Signals) => {
  const st = s.stats('id')
  return st.min > 0.02 * Math.max(st.mean, 1e-9)
}

const b2: Topology = {
  id: 'b2',
  title: 'מיישר גשר חד-פאזי (B2 / B2C)',
  rack: 'אחת מ-3 הפאזות של ספק "3×45-0-45 V" · 2 מודולי "SCR – Power Diode Half Bridge" (או דיודות) · עומס "100Ω 100W" · "50 mH"',
  summary:
    'ארבעה מתגים מחברים את המשני אל העומס כך שהמתח על העומס תמיד חיובי. עם תיריסטורים, זווית ההצתה α קובעת מתי בכל חצי מחזור מתחילה ההולכה, וכך את מתח ה-DC הממוצע.',
  physics: [
    'בגשר דיודות (α = 0) המתח על העומס הוא |v_s|: שני חצאי הגל מיושרים. הממוצע שלו הוא 2√2·V_s/π ≈ 0.9·V_s.',
    'עם תיריסטורים ועומס נגדי, ההולכה מתחילה ב-α ונגמרת כשהמתח חוצה אפס (הזרם מתאפס יחד איתו). מכאן V_d = (√2·V_s/π)·(1 + cos α).',
    'עם השראות גדולה הזרם לא מתאפס (הולכה רציפה): התיריסטור ממשיך להוליך גם כשהמתח שלילי, עד שהזוג השני מוצת. אז V_d = 0.9·V_s·cos α, ומעל α = 90° הממוצע שלילי: המעגל מחזיר אנרגיה מההשראות לרשת.',
    'הזרם ברשת אינו סינוסי. בהולכה רציפה ו-L → ∞ הוא גל מרובע, עם THD = 48.3 % ומקדם הספק 0.9·cos α.',
  ],
  params: [
    { key: 'Vs', label: 'מתח המשני (RMS)', unit: 'V', min: 5, max: 60, step: 1, def: 45 },
    { key: 'alpha', label: 'זווית הצתה α (0 = גשר דיודות)', unit: '°', min: 0, max: 170, step: 5, def: 0 },
    { key: 'R', label: 'נגד עומס', unit: 'Ω', min: 5, max: 300, step: 5, def: 100 },
    { key: 'L', label: 'השראות עומס', unit: 'mH', min: 0, max: 500, step: 10, def: 0 },
    { key: 'f', label: 'תדר הרשת', unit: 'Hz', min: 40, max: 70, step: 1, def: 50 },
  ],
  probes: [
    { key: 'vd', label: 'מתח העומס v_d', unit: 'V', expr: ['v(p)', 'v(m)'], chart: 0 },
    { key: 'id', label: 'זרם העומס i_d', unit: 'A', expr: 'i(vload)', chart: 0 },
    { key: 'vs', label: 'מתח המשני v_s', unit: 'V', expr: 'v(s1)', chart: 1 },
    { key: 'is', label: 'זרם המשני i_s', unit: 'A', expr: 'i(vin)', chart: 1 },
  ],
  netlist(p, mode) {
    const f = p.f!
    const vm = SQ2 * p.Vs!
    const load = p.L! > 0 ? `L1 x m ${p.L! / 1000}` : 'R0 x m 1u'
    const sw =
      p.alpha! > 0
        ? `X1 s1 p g1 SCR
X2 m 0 g1 SCR
X3 0 p g2 SCR
X4 m s1 g2 SCR
${gate('VG1', 'g1', f, p.alpha!, GATE_B2)}
${gate('VG2', 'g2', f, 180 + p.alpha!, GATE_B2)}`
        : `XD1 s1 p DIO
XD2 m 0 DIO
XD3 0 p DIO
XD4 m s1 DIO`
    return `B2 bridge
VS s0 0 SIN(0 ${vm} ${f})
VIN s0 s1 0
${sw}
VLOAD p y 0
RL y x ${p.R}
${load}
${models(mode)}
${SCR}
${OPTIONS}
.tran ${1 / f / 400} ${12 / f} 0 ${1 / f / 400}
.end`
  },
  timing: (p) => ({ tstop: 12 / p.f!, t0: 10 / p.f!, t1: 12 / p.f!, tmax: 1 / p.f! / 400 }),
  checks(p, s) {
    const a = p.alpha! * DEG
    const cont = continuous(s) && p.L! > 0
    const vd = s.stats('vd').mean
    const theory = cont ? 0.9 * p.Vs! * Math.cos(a) : ((SQ2 * p.Vs!) / Math.PI) * (1 + Math.cos(a))
    const id = s.stats('id').mean
    return [
      {
        key: 'Vd',
        label: cont ? 'V_d ממוצע (הולכה רציפה)' : 'V_d ממוצע (הולכה לא רציפה / עומס נגדי)',
        unit: 'V',
        sim: vd,
        theory,
        formula: cont ? 'V_d = 0.9·V_s·cos α' : 'V_d = (√2·V_s/π)·(1 + cos α)',
        tol: 0.03,
        note: cont ? undefined : 'נכון לעומס נגדי. עם L קטן הזרם לא רציף אבל מתאפס אחרי חציית האפס, והממוצע בין שתי הנוסחאות',
      },
      { key: 'Id', label: 'I_d ממוצע', unit: 'A', sim: id, theory: theory / p.R!, formula: 'I_d = V_d / R', tol: 0.03 },
      {
        key: 'THD_is',
        label: 'THD של זרם הרשת',
        unit: '%',
        sim: 100 * (s.thd('is', p.f!) ?? NaN),
        theory: cont ? 48.3 : null,
        formula: '√(π²/8 − 1) = 48.3 %',
        tol: null,
        note: 'זרם מרובע: הערך התאורטי ל-L → ∞ בלבד',
      },
    ]
  },
}

const b6: Topology = {
  id: 'b6',
  title: 'מיישר גשר תלת-פאזי (B6 / B6C)',
  rack: 'ספק "Three-Phase Power Supply 3×45-0-45 V, 2.5 A" · 3 מודולי "SCR Half Bridge" או "Diode Bridge" · "Six Pulse Controller" · עומס "100Ω 100W" · "50 mH"',
  summary:
    'שש דיודות או תיריסטורים מחברים בכל רגע את הקו הגבוה ביותר לפס העליון ואת הנמוך ביותר לתחתון. המתח על העומס הוא "כתר" של שישה פולסים בכל מחזור.',
  physics: [
    'בכל רגע מוליכה הדיודה העליונה של הפאזה הגבוהה ביותר והתחתונה של הנמוכה ביותר. לכן v_d הוא המעטפת העליונה של ששת המתחים הקוויים, ובכל מחזור שישה פולסים. ממוצע: V_d0 = 3√2·V_LL/π ≈ 1.35·V_LL.',
    'זווית ההצתה נמדדת מנקודת הקומוטציה הטבעית, 30° אחרי חציית האפס של v_a. בהולכה רציפה V_d = 1.35·V_LL·cos α. עם עומס נגדי בלבד ההולכה הופכת ללא רציפה מעל α = 60°, ואז V_d = 1.35·V_LL·[1 + cos(α + 60°)].',
    'השראות הרשת L_s מונעת מעבר מיידי של הזרם בין פאזות. בזמן החפיפה (קומוטציה) שתי פאזות מוליכות יחד, והמתח יורד בממוצע ב-ΔV = 3·ω·L_s·I_d/π. זו הסיבה שמתח המיישר יורד עם העומס גם בלי התנגדות.',
    'כל זרם פאזה הוא פולס של 120° חיובי ו-120° שלילי. עם L → ∞, THD = 31.1 % ומקדם הספק 0.955·cos α. ההרמוניות הן 6k ± 1 (5, 7, 11, 13…), ולכן מיישר 12 פולסים מבטל את 5 ו-7.',
  ],
  params: [
    { key: 'Vph', label: 'מתח פאזה (RMS)', unit: 'V', min: 10, max: 240, step: 5, def: 45 },
    { key: 'alpha', label: 'זווית הצתה α (0 = גשר דיודות)', unit: '°', min: 0, max: 150, step: 5, def: 0 },
    { key: 'R', label: 'נגד עומס', unit: 'Ω', min: 5, max: 300, step: 5, def: 100 },
    { key: 'L', label: 'השראות עומס', unit: 'mH', min: 0, max: 500, step: 10, def: 50 },
    { key: 'Ls', label: 'השראות הרשת L_s', unit: 'mH', min: 0, max: 20, step: 0.5, def: 0 },
    { key: 'f', label: 'תדר הרשת', unit: 'Hz', min: 40, max: 70, step: 1, def: 50 },
  ],
  probes: [
    { key: 'vd', label: 'מתח העומס v_d', unit: 'V', expr: ['v(p)', 'v(m)'], chart: 0 },
    { key: 'id', label: 'זרם העומס i_d', unit: 'A', expr: 'i(vload)', chart: 0 },
    { key: 'va', label: 'מתח פאזה v_a', unit: 'V', expr: 'v(a)', chart: 1 },
    { key: 'ia', label: 'זרם קו i_a', unit: 'A', expr: 'i(vsa)', chart: 1 },
  ],
  netlist(p, mode) {
    const f = p.f!
    const vm = SQ2 * p.Vph!
    const ls = p.Ls! > 0 ? (n: string) => `L${n} ${n}x ${n}1 ${p.Ls! / 1000}` : (n: string) => `R${n}s ${n}x ${n}1 1m`
    const load = p.L! > 0 ? `L1 x m ${p.L! / 1000}` : 'R0 x m 1u'
    const a = p.alpha!
    const sw =
      a > 0
        ? `XT1 a1 p g1 SCR
XT3 b1 p g3 SCR
XT5 c1 p g5 SCR
XT4 m a1 g4 SCR
XT6 m b1 g6 SCR
XT2 m c1 g2 SCR
${gate('VG1', 'g1', f, 30 + a, GATE_B6)}
${gate('VG2', 'g2', f, 90 + a, GATE_B6)}
${gate('VG3', 'g3', f, 150 + a, GATE_B6)}
${gate('VG4', 'g4', f, 210 + a, GATE_B6)}
${gate('VG5', 'g5', f, 270 + a, GATE_B6)}
${gate('VG6', 'g6', f, 330 + a, GATE_B6)}`
        : `XD1 a1 p DIO
XD3 b1 p DIO
XD5 c1 p DIO
XD4 m a1 DIO
XD6 m b1 DIO
XD2 m c1 DIO`
    return `B6 bridge
VA a 0 SIN(0 ${vm} ${f} 0 0 0)
VB b 0 SIN(0 ${vm} ${f} 0 0 -120)
VC c 0 SIN(0 ${vm} ${f} 0 0 120)
VSA a ax 0
VSB b bx 0
VSC c cx 0
${ls('a')}
${ls('b')}
${ls('c')}
${sw}
VLOAD p y 0
RL y x ${p.R}
${load}
${models(mode)}
${SCR}
${OPTIONS}
.tran ${1 / f / 600} ${12 / f} 0 ${1 / f / 600}
.end`
  },
  timing: (p) => ({ tstop: 12 / p.f!, t0: 10 / p.f!, t1: 12 / p.f!, tmax: 1 / p.f! / 600 }),
  checks(p, s) {
    const vll = SQ3 * p.Vph!
    const vd0 = (3 * SQ2 * vll) / Math.PI
    const a = p.alpha! * DEG
    const cont = continuous(s)
    const id = s.stats('id').mean
    const overlap = (3 * 2 * Math.PI * p.f! * (p.Ls! / 1000) * id) / Math.PI
    const ideal = cont || p.alpha! <= 60 ? vd0 * Math.cos(a) : vd0 * (1 + Math.cos(a + 60 * DEG))
    const theory = ideal - (cont ? overlap : 0)
    const va = s.stats('va').rms
    const ia = s.stats('ia').rms
    const pin = 3 * meanProduct(s, 'va', 'ia')
    return [
      {
        key: 'Vd',
        label: cont ? 'V_d ממוצע (הולכה רציפה)' : 'V_d ממוצע (הולכה לא רציפה)',
        unit: 'V',
        sim: s.stats('vd').mean,
        theory,
        formula:
          (cont || p.alpha! <= 60 ? 'V_d = 1.35·V_LL·cos α' : 'V_d = 1.35·V_LL·[1 + cos(α + 60°)]') +
          (cont && p.Ls! > 0 ? ' − 3·ω·L_s·I_d/π' : ''),
        tol: 0.03,
      },
      { key: 'Id', label: 'I_d ממוצע', unit: 'A', sim: id, theory: theory / p.R!, formula: 'I_d = V_d / R', tol: 0.03 },
      {
        key: 'ripple',
        label: 'אדוות המתח (שיא-לשיא)',
        unit: 'V',
        sim: s.stats('vd').pp,
        theory: p.alpha! === 0 && p.Ls! === 0 ? SQ2 * vll * (1 - Math.cos(30 * DEG)) : null,
        formula: '√2·V_LL·(1 − cos 30°)',
        note: 'גשר דיודות, L_s = 0',
        tol: 0.05,
      },
      {
        key: 'THD',
        label: 'THD של זרם הקו',
        unit: '%',
        sim: 100 * (s.thd('ia', p.f!) ?? NaN),
        theory: cont ? 31.1 : null,
        formula: '√(π²/9 − 1) = 31.1 %',
        tol: null,
        note: 'פולסים של 120°, ל-L → ∞. ל-L סופי הזרם מעוגל והערך קטן יותר',
      },
      {
        key: 'PF',
        label: 'מקדם הספק ברשת',
        unit: '',
        sim: pin / (3 * va * ia),
        theory: cont ? (3 / Math.PI) * Math.cos(a) : null,
        formula: 'λ = (3/π)·cos α ≈ 0.955·cos α',
        tol: null,
        note: 'ל-L → ∞ ו-L_s = 0',
      },
    ]
  },
}

function meanProduct(s: Signals, a: string, b: string): number {
  const x = s.get(a)
  const y = s.get(b)
  const [t0, t1] = s.window
  let acc = 0
  for (let i = 1; i < x.length && i < y.length; i++) {
    const dt = x[i]![0] - x[i - 1]![0]
    acc += 0.5 * dt * (x[i]![1] * y[i]![1] + x[i - 1]![1] * y[i - 1]![1])
  }
  return acc / (t1 - t0)
}

/* ------------------------------------------------------------------ DC-DC */

const buck: Topology = {
  id: 'buck',
  title: 'ממיר מוריד (Buck)',
  rack: '"Buck Switching Power Supply" (כניסה DC 5–30 V, יציאה 1–30 V, 0–5 A) · "DC Power Supply ±15V" לבקרה',
  summary:
    'מתג מחבר ומנתק את הכניסה במחזוריות D. הסליל והקבל מסננים את גל המלבן, וביציאה נשאר הממוצע שלו, D·V_in.',
  physics: [
    'במצב יציב המתח הממוצע על הסליל הוא אפס, אחרת הזרם היה גדל ללא גבול (איזון וולט-שנייה). כשהמתג סגור: (V_in − V_o)·D·T. כשהוא פתוח והדיודה מוליכה: −V_o·(1 − D)·T. סכום אפס נותן V_o = D·V_in.',
    'אדוות הזרם בסליל: ΔI_L = (V_in − V_o)·D·T/L. אדוות מתח היציאה: ΔV_o = ΔI_L/(8·C·f_s). לכן f_s גבוה יותר מאפשר L ו-C קטנים יותר.',
    'אם הזרם הממוצע קטן מ-ΔI_L/2, הזרם בסליל מגיע לאפס בכל מחזור (DCM), והמתח עולה מעל D·V_in: M = 2/(1 + √(1 + 4K/D²)), K = 2L/(R·T).',
  ],
  params: [
    { key: 'Vin', label: 'מתח כניסה', unit: 'V', min: 5, max: 30, step: 1, def: 24 },
    { key: 'D', label: 'מחזור עבודה D', unit: '', min: 0.05, max: 0.95, step: 0.05, def: 0.5 },
    { key: 'fs', label: 'תדר מיתוג', unit: 'kHz', min: 1, max: 100, step: 1, def: 20 },
    { key: 'L', label: 'סליל', unit: 'µH', min: 10, max: 5000, step: 10, def: 470 },
    { key: 'C', label: 'קבל', unit: 'µF', min: 1, max: 2000, step: 1, def: 100 },
    { key: 'R', label: 'נגד עומס', unit: 'Ω', min: 1, max: 500, step: 1, def: 10 },
  ],
  probes: [
    { key: 'vo', label: 'מתח היציאה v_o', unit: 'V', expr: 'v(out)', chart: 0 },
    { key: 'il', label: 'זרם הסליל i_L', unit: 'A', expr: 'i(vl)', chart: 0 },
    { key: 'vsw', label: 'מתח צומת המתג', unit: 'V', expr: 'v(sw)', chart: 1 },
    { key: 'iin', label: 'זרם הכניסה', unit: 'A', expr: 'i(vsense)', chart: 1 },
  ],
  netlist(p, mode) {
    const T = 1 / (p.fs! * 1e3)
    const { tstop, tmax } = this.timing(p)
    return `buck
VIN in0 0 DC ${p.Vin}
VSENSE in0 in 0
${gate('VG', 'g', 1 / T, 0, 360 * p.D!)}
S1 in sw g 0 SWM
D1 0 sw DMOD
VL sw l 0
L1 l out ${p.L! * 1e-6}
C1 out 0 ${p.C! * 1e-6}
R1 out 0 ${p.R}
${models(mode)}
${OPTIONS}
.tran ${tmax} ${tstop} 0 ${tmax}
.end`
  },
  timing(p) {
    const T = 1 / (p.fs! * 1e3)
    const L = p.L! * 1e-6
    const C = p.C! * 1e-6
    const settle = Math.max(10 * Math.sqrt(L * C) * Math.max(1, p.R! * Math.sqrt(C / L)), 5 * p.R! * C)
    const tstop = Math.min(Math.max(settle, 300 * T), 4000 * T)
    const n = Math.round(tstop / T)
    return { tstop: n * T, t0: (n - 20) * T, t1: n * T, tmax: T / 200 }
  },
  checks(p, s) {
    const T = 1 / (p.fs! * 1e3)
    const L = p.L! * 1e-6
    const C = p.C! * 1e-6
    const K = (2 * L) / (p.R! * T)
    const ccm = K > 1 - p.D!
    const M = ccm ? p.D! : 2 / (1 + Math.sqrt(1 + (4 * K) / (p.D! * p.D!)))
    const vo = M * p.Vin!
    const dI = ccm ? ((p.Vin! - vo) * p.D! * T) / L : null
    return [
      {
        key: 'Vo',
        label: ccm ? 'V_o ממוצע (CCM)' : 'V_o ממוצע (DCM)',
        unit: 'V',
        sim: s.stats('vo').mean,
        theory: vo,
        formula: ccm ? 'V_o = D·V_in' : 'V_o = V_in·2/(1 + √(1 + 4K/D²)), K = 2L/(R·T)',
        tol: 0.03,
      },
      { key: 'dI', label: 'אדוות זרם הסליל ΔI_L', unit: 'A', sim: s.stats('il').pp, theory: dI, formula: 'ΔI_L = (V_in − V_o)·D·T/L', tol: 0.05 },
      {
        key: 'dV',
        label: 'אדוות מתח היציאה ΔV_o',
        unit: 'V',
        sim: s.stats('vo').pp,
        theory: dI === null ? null : dI / (8 * C * p.fs! * 1e3),
        formula: 'ΔV_o = ΔI_L/(8·C·f_s)',
        tol: 0.15,
        note: 'הנוסחה מניחה שכל אדוות הזרם עוברת בקבל',
      },
      {
        key: 'eta',
        label: 'נצילות',
        unit: '%',
        sim: (100 * (s.stats('vo').rms ** 2 / p.R!)) / (p.Vin! * s.stats('iin').mean),
        theory: null,
        formula: 'η = P_out / P_in',
        tol: null,
      },
    ]
  },
}

const boost: Topology = {
  id: 'boost',
  title: 'ממיר מעלה (Boost)',
  rack: '"Boost Switching Power Supply" (כניסה DC 5–30 V, יציאה 6–40 V, 0–5 A)',
  summary: 'כשהמתג סגור הסליל אוגר אנרגיה מהכניסה. כשהוא נפתח, הסליל "דוחף" את הזרם דרך הדיודה אל היציאה, במתח גבוה מהכניסה.',
  physics: [
    'איזון וולט-שנייה על הסליל: V_in·D·T + (V_in − V_o)·(1 − D)·T = 0, ומכאן V_o = V_in/(1 − D).',
    'אדוות הזרם: ΔI_L = V_in·D·T/L. אדוות היציאה: ΔV_o = V_o·D/(R·C·f_s), כי בזמן ההולכה של המתג הקבל לבדו מזין את העומס.',
    'כש-D → 1 התאוריה האידאלית צופה מתח אינסופי. בפועל ההתנגדויות של הסליל והמתג מגבילות את ההגבר, וההפסדים גדלים מאוד. נסו "רכיבים מציאותיים" עם D = 0.9.',
  ],
  params: [
    { key: 'Vin', label: 'מתח כניסה', unit: 'V', min: 5, max: 30, step: 1, def: 12 },
    { key: 'D', label: 'מחזור עבודה D', unit: '', min: 0.05, max: 0.9, step: 0.05, def: 0.5 },
    { key: 'fs', label: 'תדר מיתוג', unit: 'kHz', min: 1, max: 100, step: 1, def: 20 },
    { key: 'L', label: 'סליל', unit: 'µH', min: 10, max: 5000, step: 10, def: 470 },
    { key: 'C', label: 'קבל', unit: 'µF', min: 1, max: 2000, step: 1, def: 100 },
    { key: 'R', label: 'נגד עומס', unit: 'Ω', min: 5, max: 500, step: 1, def: 50 },
  ],
  probes: [
    { key: 'vo', label: 'מתח היציאה v_o', unit: 'V', expr: 'v(out)', chart: 0 },
    { key: 'il', label: 'זרם הסליל i_L', unit: 'A', expr: 'i(vl)', chart: 0 },
    { key: 'vsw', label: 'מתח המתג', unit: 'V', expr: 'v(sw)', chart: 1 },
  ],
  netlist(p, mode) {
    const T = 1 / (p.fs! * 1e3)
    const { tstop, tmax } = this.timing(p)
    return `boost
VIN in 0 DC ${p.Vin}
VL in l 0
L1 l sw ${p.L! * 1e-6}
${gate('VG', 'g', 1 / T, 0, 360 * p.D!)}
S1 sw 0 g 0 SWM
D1 sw out DMOD
C1 out 0 ${p.C! * 1e-6}
R1 out 0 ${p.R}
${models(mode)}
${OPTIONS}
.ic v(out)=${p.Vin}
.tran ${tmax} ${tstop} 0 ${tmax} uic
.end`
  },
  timing(p) {
    const T = 1 / (p.fs! * 1e3)
    const L = p.L! * 1e-6
    const C = p.C! * 1e-6
    const d1 = 1 - p.D!
    const settle = Math.max(10 * Math.sqrt(L * C) / d1 * Math.max(1, p.R! * d1 * Math.sqrt(C / L)), 5 * p.R! * C)
    const tstop = Math.min(Math.max(settle, 300 * T), 4000 * T)
    const n = Math.round(tstop / T)
    return { tstop: n * T, t0: (n - 20) * T, t1: n * T, tmax: T / 200 }
  },
  checks(p, s) {
    const T = 1 / (p.fs! * 1e3)
    const L = p.L! * 1e-6
    const C = p.C! * 1e-6
    const K = (2 * L) / (p.R! * T)
    const D = p.D!
    const ccm = K > D * (1 - D) * (1 - D)
    const M = ccm ? 1 / (1 - D) : (1 + Math.sqrt(1 + (4 * D * D) / K)) / 2
    const vo = M * p.Vin!
    return [
      {
        key: 'Vo',
        label: ccm ? 'V_o ממוצע (CCM)' : 'V_o ממוצע (DCM)',
        unit: 'V',
        sim: s.stats('vo').mean,
        theory: vo,
        formula: ccm ? 'V_o = V_in/(1 − D)' : 'V_o = V_in·(1 + √(1 + 4D²/K))/2, K = 2L/(R·T)',
        tol: 0.03,
      },
      {
        key: 'dI',
        label: 'אדוות זרם הסליל ΔI_L',
        unit: 'A',
        sim: s.stats('il').pp,
        theory: ccm ? (p.Vin! * D * T) / L : null,
        formula: 'ΔI_L = V_in·D·T/L',
        tol: 0.05,
      },
      {
        key: 'dV',
        label: 'אדוות מתח היציאה ΔV_o',
        unit: 'V',
        sim: s.stats('vo').pp,
        theory: ccm ? (vo * D) / (p.R! * C * p.fs! * 1e3) : null,
        formula: 'ΔV_o = V_o·D/(R·C·f_s)',
        tol: 0.1,
      },
    ]
  },
}

/* ------------------------------------------------------------------ DC-AC */

const hbridge: Topology = {
  id: 'hbridge',
  title: 'מהפך גשר מלא עם PWM סינוסי',
  rack: '"IGBT Single-Phase Bridge Connection" (24 A, 1200 V) · "Pulse Width Modulation Controller – PWM" · עומס R-L',
  summary:
    'ארבעה מתגים מחליפים את הקוטביות של מתח ה-DC על העומס. השוואה בין סינוס לגל משולש קובעת מתי להחליף, וכך הממוצע המקומי של המתח עוקב אחרי הסינוס.',
  physics: [
    'PWM דו-קוטבי: כשהסינוס (משרעת m) גבוה מהמשולש (משרעת 1), S1 ו-S4 סגורים ו-v_ab = +V_dc. אחרת S2 ו-S3 סגורים ו-v_ab = −V_dc. הממוצע על פני מחזור מיתוג אחד הוא m·sin(ωt)·V_dc.',
    'בתחום הליניארי (m ≤ 1) ההרמוניה הבסיסית היא V_1,peak = m·V_dc. ההרמוניות של המיתוג יושבות סביב m_f = f_s/f_1 ומכפלותיו, רחוק מהבסיסית.',
    'עומס R-L הוא מסנן מעביר-נמוכים: ההרמוניות הגבוהות כמעט לא מייצרות זרם. לכן הזרם כמעט סינוסי (THD נמוך) גם כשהמתח הוא גל מלבן. I_1 = V_1/|R + jωL|.',
    'הדיודות המקבילות למתגים מעבירות את הזרם ההשראתי ברגעים שבהם הוא בכיוון ההפוך למתח. בלעדיהן היה נוצר קוצי מתח הרסני.',
  ],
  params: [
    { key: 'Vdc', label: 'מתח DC', unit: 'V', min: 10, max: 300, step: 5, def: 60 },
    { key: 'm', label: 'מקדם אפנון m_a', unit: '', min: 0.1, max: 1, step: 0.05, def: 0.8 },
    { key: 'f1', label: 'תדר יציאה', unit: 'Hz', min: 10, max: 100, step: 5, def: 50 },
    { key: 'fs', label: 'תדר מיתוג', unit: 'kHz', min: 0.5, max: 10, step: 0.5, def: 2 },
    { key: 'R', label: 'נגד עומס', unit: 'Ω', min: 1, max: 100, step: 1, def: 10 },
    { key: 'L', label: 'השראות עומס', unit: 'mH', min: 0, max: 200, step: 5, def: 20 },
  ],
  probes: [
    { key: 'vab', label: 'מתח העומס v_ab', unit: 'V', expr: ['v(a)', 'v(b)'], chart: 0 },
    { key: 'io', label: 'זרם העומס i_o', unit: 'A', expr: 'i(vload)', chart: 0 },
    { key: 'ref', label: 'סינוס הייחוס', unit: '', expr: 'v(s)', chart: 1 },
    { key: 'tri', label: 'גל נושא משולש', unit: '', expr: 'v(t)', chart: 1 },
  ],
  netlist(p, mode) {
    const Ts = 1 / (p.fs! * 1e3)
    const { tstop, tmax } = this.timing(p)
    const load = p.L! > 0 ? `L1 x b ${p.L! / 1000}` : 'R0 x b 1u'
    return `full bridge SPWM
VDC p 0 DC ${p.Vdc}
VS s 0 SIN(0 ${p.m} ${p.f1})
VT t 0 PULSE(-1 1 0 ${Ts / 2} ${Ts / 2} 1n ${Ts})
BA ga 0 V = V(s) > V(t) ? 10 : 0
BB gb 0 V = 10 - V(ga)
S1 p a ga 0 SWM
S2 a 0 gb 0 SWM
S3 p b gb 0 SWM
S4 b 0 ga 0 SWM
D1 a p DMOD
D2 0 a DMOD
D3 b p DMOD
D4 0 b DMOD
VLOAD a y 0
RL y x ${p.R}
${load}
${models(mode)}
${OPTIONS}
.tran ${tmax} ${tstop} 0 ${tmax}
.end`
  },
  timing(p) {
    const T1 = 1 / p.f1!
    const tau = p.L! / 1000 / p.R!
    const n = Math.max(4, Math.ceil((5 * tau) / T1) + 2)
    return { tstop: n * T1, t0: (n - 2) * T1, t1: n * T1, tmax: 1 / (p.fs! * 1e3) / 100 }
  },
  checks(p, s) {
    const v1 = s.harmonic('vab', p.f1!, 1)
    const th1 = (p.m! * p.Vdc!) / SQ2
    const z = Math.hypot(p.R!, 2 * Math.PI * p.f1! * (p.L! / 1000))
    return [
      { key: 'V1', label: 'V_1 (RMS של הבסיסית)', unit: 'V', sim: v1, theory: th1, formula: 'V_1 = m_a·V_dc/√2', tol: 0.03 },
      { key: 'I1', label: 'I_1 (RMS של הבסיסית)', unit: 'A', sim: s.harmonic('io', p.f1!, 1), theory: th1 / z, formula: 'I_1 = V_1/|R + jωL|', tol: 0.03 },
      { key: 'THDi', label: 'THD של זרם העומס', unit: '%', sim: 100 * (s.thd('io', p.f1!) ?? NaN), theory: null, formula: '—',
        note: 'L מסנן את הרמוניות המיתוג: הזרם כמעט סינוסי', tol: null },
      { key: 'Vrms', label: 'RMS של v_ab', unit: 'V', sim: s.stats('vab').rms, theory: p.Vdc!, formula: 'RMS(±V_dc) = V_dc', tol: 0.02 },
    ]
  },
}

export const TOPOLOGIES: Topology[] = [b2, b6, buck, boost, hbridge]

export function defaults(t: Topology): P {
  return Object.fromEntries(t.params.map((q) => [q.key, q.def]))
}
