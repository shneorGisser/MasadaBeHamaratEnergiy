# Scripting — Python in the browser (S1)

Each project has a "סקריפט" (script) tab: a Python 3 editor whose scripts run studies of the
project. It is meant for parametric sweeps and processing in the style of MATLAB.

## Why it runs in the browser (Pyodide) and not on the server

Running user code on the server would mean running arbitrary code on the machine that holds
every group's data. The browser's WebAssembly sandbox gives that isolation for free.

* Python (Pyodide) runs in a Web Worker, so a long script never freezes the page, and "stop"
  simply terminates the worker.
* The only bridge to the server is the same HTTP API the UI uses. A script can only do what
  the user could do by clicking.

Pyodide is copied from the `pyodide` npm package (MPL-2.0) into `dist/pyodide/` at build time
(`vite-plugins/pyodide-assets.ts`) and served from the same origin. There is no CDN, so it
works in a closed lab network.

* The first run loads about 13 MB, which takes roughly 10 s.
* Only the standard library is available. numpy and the other Pyodide packages are not
  bundled.

## API: the `vlab` module (`frontend/src/scripting/prelude.py`)

| Call | Returns |
|---|---|
| `await vlab.studies()` | `{kind: default_case}` of the project |
| `await vlab.spec()` | the equipment spec (read-only) |
| `await vlab.run(study, label="", **case)` | the run. The case is the defaults overridden by the arguments. A failed run raises `RunFailed` with the server's message. |
| `vlab.table(r, id=None)` / `vlab.column(r, key, id=None)` | the rows of a table, or one column of it |
| `vlab.param(r, key)` | the value of a computed parameter |
| `vlab.plot(x, *ys, title, xlabel, ylabel, labels, log)` | draws a chart in the output pane, using the app's own chart |

**Every run a script makes is an ordinary run of the project.** It is immutable, labelled
`script: …`, and appears in the study's history, in comparisons and in reports. Nothing is
computed in the browser except what the script itself computes.

Examples are available in the tab:

* an introduction;
* closing current against phase error (synchronising);
* starting current against ramp time (V/f);
* bench voltage against load, and the loop impedance (network).

The editor's draft is kept in localStorage, per project and per browser.

## Tests

* `test_script_prelude.py` exercises the prelude in CPython with a fake bridge:
  * the defaults merge;
  * the helpers find data;
  * a failed run raises an exception;
  * a malformed plot is rejected.
* E2E P1 runs real Pyodide in the browser and checks that:
  * the sweep produces a chart;
  * a failed run produces `RunFailed`;
  * the script's runs appear in the study's history.

## Also in this change: a security fix

The SPA fallback served `static/<path>` without resolving the path. An encoded `../` could
read files outside the build directory, and the new test demonstrated this on the old code.
The path is now resolved and must stay inside the static directory (`test_static_spa.py`).
