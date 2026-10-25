/** Example scripts. The generic one works in every project; the others need their study. */
export interface Example {
  id: string
  title: string
  /** experiment ids where it applies; empty = every experiment */
  experiments: string[]
  code: string
}

export const EXAMPLES: Example[] = [
  {
    id: 'intro',
    title: 'היכרות: הניסויים של הפרויקט והרצה אחת',
    experiments: [],
    code: `import vlab

studies = await vlab.studies()
print("studies:", ", ".join(studies))

kind = next(iter(studies))
r = await vlab.run(kind, label="intro")
print(kind, "→", r["status"])
for p in r["result"]["parameters"][:8]:
    print(f'  {p["key"]:>14} = {p["value"]} {p["unit"]}')
`,
  },
  {
    id: 'sync_angle',
    title: 'סנכרון: זרם הסגירה כפונקציה של הפרש הפאזה',
    experiments: ['synchronous'],
    code: `import vlab

angles = [0, 10, 20, 40, 60, 90]
peak, est = [], []
for a in angles:
    r = await vlab.run("synchronize", label=f"angle {a}", angle_deg=a, df=0.0, t_end=0.5)
    peak.append(vlab.param(r, "I_peak"))
    est.append(vlab.param(r, "I2_est"))
    print(f"Δθ = {a:3d}°  I_peak = {peak[-1]:.3f} A")

vlab.plot(angles, peak, est, title="Closing current vs phase error",
          xlabel="Δθ [°]", ylabel="I [A]", labels=["I_peak (simulation)", "|ΔU|/X''d"])
`,
  },
  {
    id: 'vf_ramp',
    title: 'מהפך: שיא זרם ההתנעה כפונקציה של זמן הרמפה',
    experiments: ['induction_motor'],
    code: `import vlab

ramps = [0.0, 0.1, 0.2, 0.5, 1.0, 2.0]
ratio = []
for tr in ramps:
    r = await vlab.run("vf_start", label=f"ramp {tr}", t_ramp=tr, t_end=tr + 1.0)
    ratio.append(vlab.param(r, "I_ratio_dol"))
    print(f"t_ramp = {tr:4.1f} s  I_peak / I_peak,DOL = {ratio[-1]:.3f}")

vlab.plot(ramps, ratio, title="Starting current vs ramp time",
          xlabel="t_ramp [s]", ylabel="I_peak / I_DOL")
`,
  },
  {
    id: 'net_drop',
    title: 'רשת: מפל המתח ועכבת הלולאה בעמדה',
    experiments: ['network'],
    code: `import vlab

lf = await vlab.run("load_flow", label="sweep", scales=[0, 0.5, 1, 1.5, 2, 3])
p = vlab.column(lf, "P_kW", "sweep")
u3 = vlab.column(lf, "u_B3", "sweep")
vlab.plot(p, u3, title="Bench voltage vs building load", xlabel="P [kW]", ylabel="U_B3 [%]")

sc = await vlab.run("short_circuit", label="loop")
z = vlab.param(sc, "Z_loop_B3")
print(f"Z_loop at the bench = {z:.4f} Ω  →  I = 230/Z = {230 / z:.0f} A")
`,
  },
]

export function examplesFor(experimentId: string): Example[] {
  return EXAMPLES.filter((e) => e.experiments.length === 0 || e.experiments.includes(experimentId))
}
