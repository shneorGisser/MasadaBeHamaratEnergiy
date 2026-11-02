# DXF export of the schematic (X1)

The circuit editor has an "ייצוא DXF" (export DXF) button. It writes the schematic exactly as
it is drawn on screen, as a DXF R12 (ASCII) file.

## Why R12

Every CAD program reads it: AutoCAD, LibreCAD, QCAD and DraftSight. It needs no handles and no
OBJECTS section, so a writer of about 150 lines (`frontend/src/schematic/dxf.ts`) produces a
valid file without a dependency.

## Geometry

The geometry is taken from React Flow, not from a separate model:

* the measured component boxes;
* the real handle positions;
* the same smooth-step routing as on screen, with square corners.

1 px is 0.25 mm, and y is flipped so it points up.

| Layer | Contents |
|---|---|
| `COMPONENTS` | the outlines |
| `TERMINALS` | a circle for each terminal, with its name |
| `WIRES` | the wire segments and junction dots, placed where three or more conductors meet or a wire ends on another wire |
| `TEXT` | the component id and type |

## Limitations

* **Text is ASCII only.** R12 TEXT is single-byte, and the \U+XXXX escape is not understood by
  every reader. ezdxf's renderer printed it literally. The drawing therefore carries the
  engineering references (component ids, types and terminal names), and the Hebrew labels stay
  in the app.
* **Symbols are boxes.** The app's symbols (meter dials and so on) are drawn as labelled boxes.
* **The routing is the screen's routing.** Where the template layout makes a wire cross a
  component box or run along another wire, the DXF shows the same thing. One example is the
  load-test template, where a1/b1 run through V2. Improving the routing (an orthogonal router,
  or fixed template coordinates) is a separate task.

## Verification

* **Unit tests (`dxf.test.ts`):**
  * the R12 structure;
  * the four layers;
  * mm with the y flip;
  * ASCII text;
  * path parsing;
  * junction dots.
* **E2E D1:** the load-test circuit is exported. Every free end of a wire must fall exactly on
  a terminal circle, which checks that the wires are attached.
* **Inspection:** the exported file was opened with ezdxf. The audit found 0 errors, and the
  file was rendered to PNG and checked by eye.

## Sheet and title block

The export is placed on the smallest landscape ISO A sheet (A4 to A0) that holds it at 1:1. The
frame follows ISO 5457: a 20 mm binding margin on the left, 10 mm on the other sides. In the
bottom-right corner is an ISO 7200-style title block, 180 mm wide, with these fields:
- title;
- drawing (experiment / study);
- project;
- date;
- scale and sheet;
- empty "drawn by" and "checked" fields for the students' names.

Everything is on its own `FRAME` layer. The fields are ASCII, like the rest of the R12 text. A
Hebrew project name is replaced by "project <id>" rather than turned into question marks.
Checked by rendering the exported file with ezdxf: the frame, the title block and the
schematic land where they should.
