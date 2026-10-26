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

## Layouts of the templates (L2)

**Mirrored components.** A component can now be drawn mirrored left↔right.

* The `flip` field in the layout is for drawing only, and the netlist ignores it.
* In the editor it is the "הפוך ↔" (flip) button.
* This lets a meter in a chain that runs right to left keep its polarity marks and still face its
  neighbours. In the generator circuits of experiment 3, power flows from G on the right to the
  load on the left.

**Readability metric.** `drawingMetrics.ts` measures each drawing by:

* crossings between different nets;
* bends;
* detour (routed length divided by the Manhattan distance);
* total length.

**Optimiser.** `tools/layout-optimize.test.ts` is a dev tool and is not part of the suite.

* It runs a seeded local search over positions and flips.
* Components shared by several templates, such as those placed by the same helper function, keep
  one position across all of them.
* Its positions were written into the templates by hand and checked visually, because the
  metric is a guide and not a judge: an early weighting gave fewer crossings but a worse
  drawing.

**Result.** Crossings between different nets, before → after:

| Template | Before | After |
|---|---|---|
| Induction regulator | 16 | 7 |
| Synchronous generator (4 studies) | 13 | 7 |
| Wound rotor with Rst | 12 | 6 |
| Transformer, no load YY | 15 | 12 |
| Transformer, no load YD | 18 | 15 |
| Transformer, load | 22 | 18 |

**What remains.** The meters now sit next to what they measure, with no detour around the
machine.

**Guard.** `router.test.ts` fails if any template exceeds 18 crossings, 60 bends or a worst
detour of 2.5. That is "no worse than the worst one today".

**Not yet possible.** Rotating a component by 90° is not supported. A voltmeter whose two
leads go to the same side of a machine still needs one lead to wrap around it.
