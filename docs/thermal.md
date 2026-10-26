# Winding temperature — R(T) (H1)

The resistances in a machine spec are measured cold, at the lab's ambient temperature (T_ref).
In a load test the windings warm up, and copper resistance rises with temperature:

    R(T) = R(T_ref) · (235 + T) / (235 + T_ref)        (copper; IEC 60034-1, IEC 60076-1)

For example, going from 20 °C to 75 °C raises every copper resistance by 21.6 %, and with it
the copper losses and the voltage drops.

## In the model (`vel/experiments/thermal.py`)

**The spec field.** Every machine spec has a `thermal` section:

* **T_ref:** the temperature at which the R values hold.
* **T_op:** the winding temperature during the load tests.

**When it applies.** The correction is applied once, where a study runs
(`services.runs.execute_snapshot` and the live operating point). It scales only the copper
resistances of the equivalent circuit:

| Experiment | Resistances scaled |
|---|---|
| Transformer | R1, R2 |
| Induction motor | R1, R2' |
| Synchronous | Ra, R_f |
| Wound rotor | R1, R2 |
| DC machine | R_a, R_f, R_s |

**What it changes.**

* **Cold studies.** The DC-resistance and insulation studies keep T_ref, because they are done
  on a cold machine.
* **Warning.** When a correction is applied, the run says so in the `winding_temperature`
  warning, with the factor.
* **Old projects and runs.** With T_op = T_ref (the default) nothing changes. A stored spec
  without `thermal` validates with the default, so every earlier run reproduces bit for bit.

## Not modelled

* The temperature rise itself. T_op is an input, measured with a thermometer or by the
  resistance method.
* The temperature dependence of the iron and of the brush drop.
* Aluminium windings, which would use 225 in place of 235.

## Tests (`test_thermal.py`)

* **Factor:** the copper factor is computed correctly.
* **Every machine:** scaling touches exactly its copper fields. Cold studies and the default
  setting leave the spec as it is.
* **Transformer short circuit:** r_k rises by the factor.
* **Old specs:** a spec without the `thermal` section validates.
* **E2E TH1:** T_op = 75 °C is entered in the form, and the warning appears in the run.
