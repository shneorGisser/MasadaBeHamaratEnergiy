# Scope tools on time charts (O1)

Every chart whose x axis is time (`x = "t"`) is drawn as a `ScopeChart`, which works like an
oscilloscope:

1. Click the chart once to place cursor A, and again to place cursor B. A third click starts
   over.
2. A table then shows, for each trace:
   * the value at A and at B, and Δy;
   * over [A, B]: the mean, the RMS and the peak-to-peak value;
   * Δt and 1/Δt.
3. **Harmonics.** Choose a trace and f₀ (default 50 Hz). The table shows harmonics 1–15:
   * the RMS value, the share of the fundamental and the phase;
   * the THD (relative to the fundamental) and the DC component.

   They are computed over the largest whole number of periods of f₀ that starts at A and fits
   before B.

## Method (`frontend/src/components/scope.ts`)

The trace is used exactly as it was sampled: there is no resampling and no invented point.

* **Statistics and Fourier coefficients** come from trapezoidal integration over the samples,
  so a trace decimated for the run table (non-uniform spacing) is handled correctly.
* **Window ends** are interpolated linearly.
* **Highest harmonic.** It is limited to a quarter of the samples per period, so the table
  never shows harmonics the trace cannot resolve.

## Physics this exposes

The inrush current of the transformer is rich in the second harmonic. With the default
energising it is about 37 % of the fundamental in the first two cycles. The `inrush` study now
reports it as the `H2_ratio` parameter.

This is the signature a differential relay uses to block tripping on inrush, at a setting of
about 15 %.

## Tests

* **Unit tests (`scope.test.ts`):**
  * the RMS of a sine is A/√2 and its mean is 0;
  * a 5 % third harmonic with an offset is recovered, with THD = 5 %, on an irregularly thinned
    trace;
  * a window shorter than one period is refused;
  * a cursor outside the trace has no value.
* **Backend test TT9:** H₂/H₁ > 15 % for the default inrush.
* **E2E O1:** cursors are placed on the inrush chart, and the RMS and THD tables appear.
