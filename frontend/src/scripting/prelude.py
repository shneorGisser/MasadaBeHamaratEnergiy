"""vlab — the scripting API of the virtual lab (runs inside Pyodide, in the browser).

Every simulation goes through the server's run API, so a script's runs are ordinary immutable
runs of the project (labelled "script: …"), visible in the study's run history and in reports.
Nothing is computed in the browser except what the script itself computes."""

import json

import _vlab_js

__all__ = ["run", "table", "column", "param", "plot", "studies", "spec"]


class RunFailed(Exception):
    """The server ran the study and it failed (invalid input, no convergence, …)."""


async def studies():
    """The project's study kinds and their default cases: {kind: default_case}."""
    out = json.loads(await _vlab_js.studies())
    return {s["kind"]: s["default_case"] for s in out}


async def spec():
    """The project's equipment spec (read-only here; edit it in the spec tab)."""
    return json.loads(await _vlab_js.spec())


async def run(study, label="", **case):
    """Run a study with the given case fields (the rest from the study's defaults).

    Returns the run: {"id", "status", "result": {"tables", "parameters", "curves"}, "warnings"}.
    A failed run raises RunFailed with the server's message — never a silent empty result."""
    defaults = (await studies()).get(study)
    if defaults is None:
        raise KeyError(f"no study {study!r} in this project")
    body = {**defaults, **case}
    r = json.loads(await _vlab_js.run(study, json.dumps(body), label or "script"))
    if r.get("status") not in ("success", "success_with_warnings"):
        msg = (r.get("error") or {}).get("message", r.get("status"))
        raise RunFailed(f"{study}: {msg}")
    return r


def table(r, table_id=None):
    """Rows (list of dicts) of a run's table — the first one when table_id is None."""
    tables = r["result"]["tables"]
    if table_id is None:
        return tables[0]["rows"]
    for t in tables:
        if t["id"] == table_id:
            return t["rows"]
    raise KeyError(f"no table {table_id!r}; tables: {[t['id'] for t in tables]}")


def column(r, key, table_id=None):
    """One column of a table as a list (None where the cell is empty)."""
    return [row.get(key) for row in table(r, table_id)]


def param(r, key):
    """Value of a computed parameter (None when it is undefined, with the reason in the run)."""
    for p in r["result"]["parameters"]:
        if p["key"] == key:
            return p["value"]
    raise KeyError(f"no parameter {key!r}")


def plot(x, *ys, title="", xlabel="", ylabel="", labels=None, log=False):
    """Draw up to six series against x in the output pane (the app's own chart)."""
    if not ys:
        raise ValueError("plot(x, y, …) needs at least one y series")
    series = []
    for i, y in enumerate(ys[:6]):
        if len(y) != len(x):
            raise ValueError(f"series {i + 1} has {len(y)} points, x has {len(x)}")
        name = labels[i] if labels and i < len(labels) else f"y{i + 1}"
        series.append({"name": name, "y": [None if v is None else float(v) for v in y]})
    _vlab_js.plot(
        json.dumps(
            {
                "title": title,
                "xlabel": xlabel,
                "ylabel": ylabel,
                "log": bool(log),
                "x": [float(v) for v in x],
                "series": series,
            }
        )
    )
