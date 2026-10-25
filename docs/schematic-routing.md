# Wire routing and drawing audit (L1)

## The problem

The editor drew cables with React Flow's "smooth step" path, which ignores obstacles. I audited
all 30 template circuits through their DXF exports, and 5 of the 6 experiments failed. The
failures were wires running through component outlines (for example, a1/b1 running through V2)
and wires of different nets running along each other. Both kinds of drawing suggest connections
that do not exist.

## The router (`frontend/src/schematic/router.ts`)

**Inputs.** The router is a pure function of the circuit: node sizes (`nodeSize`), terminal
slots and positions. It needs no DOM measurement, so the screen, the DXF export and the tests
all see the same drawing.

**Search.**

* A* over a grid of 10 px lanes plus the coordinates of every terminal stub. The state is
  (point, heading).
* Cost = length + bend penalty + the penalties below.
* Wires are routed shortest first, and each routed wire is reserved for the ones after it.

| Situation | Penalty |
|---|---|
| Running along another net | 4000 |
| Ending or bending on another net's line, or passing through its end | 2000 |
| Crossing another net | 25 |
| Running in a lane closer than 10 px to another net | 3 per px |

**Obstacles.** Each component outline, together with the id label above it, plus a 12 px
margin.

**Terminals.**

* Every terminal leaves its node perpendicular to its side, through a stub that extends until it
  is clear of every outline.
* Two terminals that face each other across a narrow gap (a meter next to a meter) are joined by
  a straight Z.
* Nodes with terminals on top (DC machine, synchronous machine) carry the id label inside the
  outline, so the label does not sit on the wires.

**Junction dots.** Dots are drawn wherever three conductors meet, on screen and in the DXF.

**While dragging.** The edges fall back to smooth step while a node is dragged and are
re-routed on release.

## Rules (`drawingAudit.ts`)

| Rule | What it forbids |
|---|---|
| A | A wire through an outline or through an id label |
| B | Wires of different nets running along each other |
| C | A wire ending or bending on a wire of another net (a false junction) |
| D | A wire passing over a terminal of another net |

A plain crossing is allowed, because it carries no dot.

## Tests

* **`router.test.ts`:** all 36 templates, including the variants, are routed and audited. Each
  one is clean and takes less than 1.5 s; in practice each takes between 3 and 110 ms.
  * The templates come from `__fixtures__/templates.json`, written by
    `scripts/export_templates.py`.
  * `backend/tests/test_template_fixture.py` fails if a template changes without regenerating
    the fixture.
* **E2E L1:** the audit runs again on the DXF that the browser actually exports, for every study
  of the 6 experiments.
* **E2E D1:** every free end of a wire lands on a terminal.

## Template change

In the transformer no-load template, V2 and V2ph moved from x = 860 to x = 900. The 40 px
corridor beside T's secondary had room for one lane only, so two nets were forced onto the same
line.

## What remains

The rules guarantee an unambiguous drawing, not a beautiful one. Some templates (the induction
regulator, the transformer load test) still route long detours around the meters, because the
meters sit far from what they measure. Fixing that is a matter of moving the meters in the
templates, one by one.
