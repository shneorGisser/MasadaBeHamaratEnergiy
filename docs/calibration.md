# Calibrating the model to a measurement set (K1)

The "כיול המודל לסט המדידות" (calibrate the model to the measurement set) box appears under every
measurement set (`POST /api/measurement-sets/{id}/calibrate`, `services/calibration.py`).

## Why a service and not the fit scripts

The old `scripts/fit_*.py` fitted the 2025 reports once each, by hand. Here the residual is the
comparison the student already sees:

* the same case at the measured operating points;
* the same pairing of rows;
* the same quantities, including the derived columns.

So "calibrated" means exactly "the comparison table got smaller". It works for any measurement
set of any machine, including the photos and tables from the lab.

## Method

* **Knobs.** Each knob scales one or more spec fields by a single factor. Several fields share a
  knob when the data sees only their combination: R1 + R2 and X1 + X2 in a short-circuit test,
  and X1 + X2' in a locked-rotor test.
  * `DEFAULT_KNOBS` holds the identifiable knobs for 28 studies across 6 machines, and a test
    checks that each one points at a positive spec field.
  * The API also accepts any knobs (`{"knobs": [["ecm.R1"], ["ecm.X1","ecm.X2"]]}`).
* **Search.** least_squares over ln(factor), bounded to ×0.1…×10, starting from the current
  spec.
* **Residuals.** (measured − simulated)/measured for every cell compared at the start.
  * A cell that loses its partner (a failed run, an unmatched row) costs 1.
  * A cell the model gives exactly 0 (a phenomenon it does not model, such as the hysteresis
    width dE) is excluded and reported.
* **Temperature.** The fitted values are those of the spec as stored, at T_ref. The runs apply
  the winding temperature as usual.

## Honesty

The result reports:

* the error before and after (RMS and maximum);
* for each knob, the factor and a relative standard uncertainty from the Jacobian
  (s²·(JᵀJ)⁻¹);
* the correlation between knobs. |ρ| > 0.95 means the data cannot separate them, and only their
  combination is determined;
* a warning for a knob that ended on a bound ("the measurements do not determine it, or there is
  a measurement error; do not apply without checking");
* a warning for a knob determined poorly (relative uncertainty > 50 %);
* the cells left out.

Nothing is saved until the student clicks "החל" (apply). The applied spec is then marked "fitted",
and its provenance note names the set and the factors. Earlier runs stay as they were.

## Example: the real data of 2025

These runs were checked against the 2025 report data.

* **Synchronous machine, short circuit.** k_a ×0.472 (±3.7 %). The RMS error falls from 44.6 %
  to 10.1 %.
* **Synchronous machine, OCC with a, I_s and m.** The RMS error falls from 9.7 % to 5.9 %. I_s and
  m are reported as correlated (ρ = −0.99): the measured range does not determine the shape of
  the knee. The hysteresis width is excluded, because the model gives it 0.

## Tests (`test_calibration.py`)

* Synthetic measurements made from a known "true" machine:
  * short circuit: R ×1.3 and X ×0.8 are recovered to 1e-3, and nothing is saved;
  * induction motor, no load: Xm ×1.15 and R_fe ×0.85 are recovered.
* R1 and R2 as separate knobs in a short-circuit test are flagged, and an unknown field is
  refused.
* Every default knob is valid.
* E2E C1 calibrates the 2025 table, applies the result and checks the provenance note.
