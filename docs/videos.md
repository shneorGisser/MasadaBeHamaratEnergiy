# Explanation videos

Five short videos (40–60 s each), one per core idea of the course. They are made with
**Manim Community** (MIT) and shown on `/videos`, with a transcript under each player. Each
experiment's page links to its videos.

| Video | Experiment | Data in it |
|---|---|---|
| `RotatingField`: the rotating magnetic field | 2, 3, 4 | the sum of three phase MMFs (the textbook definition, computed in the scene); slip from the 2026 sheet |
| `TorqueSpeed`: torque–speed characteristic | 2, 4 | the torque–speed table of the `ap3030_sheet_2026` fit; Kloss; the 2026 load readings |
| `TransformerTests`: no-load and short-circuit tests | 1 | the no-load and short-circuit studies of the `report_2025` transformer; the 2025 table |
| `SyncOccScc`: OCC, SCC and X_s | 3 | the OCC and SCC studies of the fitted machine; the 2026 readings |
| `VCurves`: V-curves | 3 | the V-curve study at P = 0, 100 and 200 W |

## Why from code

A curve in a video must be the curve the app draws. `scripts/video_data.py` runs the app's own
studies through the API and takes measured points from `vel.labdata`, writing them to
`videos/data.json`. The scenes only draw that data.

When a model changes, re-running the two scripts updates the videos.

The videos are honest about the data:
* the AP-3030 plate does not fit the sheet;
* the 2025 transformer table records a phase voltage in a line-voltage column;
* two Ik3 readings of the 2026 sheet break the line and the ratio to Ik2.

## Rebuilding

```bash
.venv/bin/pip install "manim==0.19.*" "manim-voiceover==0.3.*" "setuptools<81"
cd backend && ../.venv/bin/python ../scripts/video_data.py && cd ..
.venv/bin/python videos/render_all.py -qm        # 720p30 → frontend/public/videos
```

Each video is written twice:
* **WebM (VP9)**, because open-source Chromium builds cannot decode H.264;
* **H.264 mp4**.

The captions are burned into the picture. `<video>.vtt` and `<video>.json` carry the same cues.

## Narration

The videos are silent with burned-in Hebrew captions. `videos/common.py` can voice them through
manim-voiceover:
* `VEL_TTS=recorder` records your own voice at render time. This is the safe choice for licensing
  and usually the best for teaching.
* `VEL_TTS=gtts` uses Google TTS and needs internet.

The research (2026-10) found no open Hebrew TTS whose model weights are cleared for commercial
use:
* phonikud-tts and MMS-TTS are non-commercial;
* BlueTTS needs a licence check.

For JCT-only teaching use, phonikud-tts or MMS fit as a custom speech service. The models could
not be downloaded from this environment.

## Technical notes

* Hebrew text uses `MarkupText`. manim 0.19's `Text` drops some right-to-left strings entirely;
  for example, "קלוס" renders with zero glyphs.
* Formulas are LaTeX (`MathTex`) and never mixed into a right-to-left text run.
* Measured points are hollow circles, so they are told apart by shape as well as by colour.
