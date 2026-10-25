"""Compare a student's circuit with the manual's wiring (the study's template), by nets.

A circuit is wired correctly when the same terminals are joined — not when the cables look
alike: two cables to one terminal or one cable through a bridge are the same net. So both
circuits are reduced to nets (union-find over the wires) and compared:

* a template net whose terminals fall into two or more of the student's nets is a missing
  connection (the student's groups are listed, so the gap is visible);
* a student net that joins terminals of two or more template nets — or a terminal the manual
  leaves free — is an extra connection (often a short);
* components the manual has and the student does not, and the reverse.

Several variants of a study (connection groups) each have a template; the closest one is used.
A difference is not necessarily an error — an ammeter on the other side of a wattmeter's
current coil measures the same current — so the result is "differs from the manual", with
the evidence, and the simulation still runs whatever is wired.
"""

from __future__ import annotations

from typing import Any

from vel.engine.circuit import CircuitModel

Term = str  # "component.terminal"


def nets(c: CircuitModel) -> dict[Term, Term]:
    """Terminal → representative of its net, for every terminal that has a wire."""
    parent: dict[Term, Term] = {}

    def find(x: Term) -> Term:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for w in c.wires:
        a = find(f"{w.a.component}.{w.a.terminal}")
        b = find(f"{w.b.component}.{w.b.terminal}")
        if a != b:
            parent[b] = a
    return {t: find(t) for t in list(parent)}


def _groups(terms: list[Term], net: dict[Term, Term]) -> list[list[Term]]:
    g: dict[Term, list[Term]] = {}
    for t in terms:
        g.setdefault(net.get(t, t), []).append(t)  # unwired terminal = its own group
    return sorted((sorted(v) for v in g.values()), key=lambda v: v[0])


def compare(student: CircuitModel, template: CircuitModel) -> dict[str, Any]:
    s_comp = {c.id for c in student.components}
    t_comp = {c.id for c in template.components}
    common = s_comp & t_comp
    sn, tn = nets(student), nets(template)

    def by_root(n: dict[Term, Term]) -> dict[Term, list[Term]]:
        out: dict[Term, list[Term]] = {}
        for t, r in n.items():
            if t.split(".")[0] in common:
                out.setdefault(r, []).append(t)
        return out

    missing = []
    for terms in by_root(tn).values():
        if len(terms) < 2:
            continue
        g = _groups(terms, sn)
        if len(g) > 1:
            missing.append({"net": sorted(terms), "student_groups": g})
    extra = []
    for terms in by_root(sn).values():
        if len(terms) < 2:
            continue
        g = _groups(terms, tn)
        if len(g) > 1:
            extra.append({"net": sorted(terms), "template_groups": g})
    return {
        "missing_components": sorted(t_comp - s_comp),
        "extra_components": sorted(s_comp - t_comp),
        "missing_connections": sorted(missing, key=lambda m: m["net"][0]),
        "extra_connections": sorted(extra, key=lambda m: m["net"][0]),
    }


def _score(r: dict[str, Any]) -> int:
    return (
        len(r["missing_components"])
        + len(r["extra_components"])
        + len(r["missing_connections"])
        + len(r["extra_connections"])
    )


def messages(r: dict[str, Any]) -> list[str]:
    out = [f"רכיב שבחוברת חסר במעגל: {c}" for c in r["missing_components"]]
    out += [f"רכיב שאינו בחוברת: {c} (חיבוריו לא נבדקו)" for c in r["extra_components"]]
    for m in r["missing_connections"]:
        parts = " | ".join(" · ".join(g) for g in m["student_groups"])
        out.append(f"חסר חיבור: בחוברת {', '.join(m['net'])} מחוברים יחד; אצלך הם בקבוצות {parts}")
    for m in r["extra_connections"]:
        parts = " | ".join(" · ".join(g) for g in m["template_groups"])
        out.append(
            f"חיבור שאינו בחוברת: אצלך {', '.join(m['net'])} מחוברים יחד; בחוברת אלה צמתים "
            f"נפרדים ({parts}) — בדקו שאין קצר"
        )
    return out


def check(student: CircuitModel, templates: dict[str, CircuitModel]) -> dict[str, Any]:
    """Compare with every template (variant) and report against the closest one."""
    results = {v: compare(student, t) for v, t in templates.items()}
    variant = min(results, key=lambda v: (_score(results[v]), v))
    r = results[variant]
    return {
        "variant": variant,
        "matches": _score(r) == 0,
        **r,
        "messages": messages(r),
    }
