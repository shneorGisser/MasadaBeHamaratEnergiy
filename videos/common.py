"""Shared pieces of the explanation videos: Hebrew text, the caption bar, narration timing,
transcripts, and the lab's model data.

Narration. Each scene speaks through `say()`. Without a speech service (the default), the
caption is shown for a reading time of ~2.4 words per second, the animations play inside that
time, and the video is silent. With VEL_TTS=gtts (Google TTS through manim-voiceover, needs
internet) or VEL_TTS=recorder (your own voice, recorded at render time), the same text is
spoken and the timing follows the audio. Either way the captions are burned into the video and
written to <scene>.vtt and <scene>.json (the transcript the app shows under the player).
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Animation,
    FadeIn,
    FadeOut,
    MarkupText,
    MathTex,
    Mobject,
    Rectangle,
    VGroup,
    Wait,
    config,
)
from manim.animation.animation import prepare_animation
from manim_voiceover import VoiceoverScene

HERE = Path(__file__).resolve().parent
OUT = Path(
    os.environ.get("VEL_VIDEO_OUT", HERE.parent / "frontend" / "public" / "videos")
)
FONT = "Noto Sans Hebrew"

# the app's palette (frontend/src/styles.css): simulation, measurement, theory
BG = "#0f1b26"
INK = "#e7edf2"
INK2 = "#9fb3c4"
SIM = "#4c9be0"
MEAS = "#e0795c"
THEORY = "#8fb85a"
ACCENT = "#e0a83c"
PH = ("#e05c5c", "#e0c14c", "#5ca8e0")  # phases a, b, c

config.background_color = BG

_LTR_RUN = re.compile(
    r"([A-Za-z0-9(][A-Za-z0-9_.,=+\-·/()°%Ω√²′ ]*[A-Za-z0-9)°%Ω²′]|[A-Za-z0-9])"
)


def iso(s: str) -> str:
    """Wrap Latin/number runs in Unicode isolates (LRI…PDI), so '50 Hz' or '(p = 4)' stays
    in one piece inside a right-to-left sentence."""
    return _LTR_RUN.sub(lambda m: "\u2066" + m.group(1) + "\u2069", s)


def he(
    s: str, size: float = 26, color: str = INK, weight: str = "NORMAL"
) -> MarkupText:
    """Hebrew text. MarkupText, not Text: manim 0.19's Text drops some right-to-left strings
    entirely (e.g. 'קלוס' renders with zero glyphs), MarkupText renders them all."""
    body = html.escape(iso(s), quote=False)
    if weight == "BOLD":
        body = f"<b>{body}</b>"
    return MarkupText(body, font=FONT, font_size=size, color=color)


def mt(tex: str, size: float = 30, color: str = INK) -> MathTex:
    """A formula, typeset by LaTeX: never mixed into a right-to-left Text run."""
    return MathTex(tex, font_size=size, color=color)


def labeled(
    label: str, tex: str, size: float = 30, color: str = INK, label_color: str = INK2
) -> VGroup:
    """Hebrew label on the right, formula on its left (reading order in Hebrew)."""
    return VGroup(mt(tex, size, color), he(label, size * 0.7, label_color)).arrange(
        RIGHT, buff=0.25
    )


def data() -> dict[str, Any]:
    return json.loads((HERE / "data.json").read_text())


def _vtt_time(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


class LabScene(VoiceoverScene):
    """Base scene: a title, the caption bar, say(), and the transcript on exit."""

    title_he = ""

    def setup(self) -> None:
        super().setup()
        self._cues: list[tuple[float, float, str]] = []
        self._caption: Mobject | None = None
        tts = os.environ.get("VEL_TTS", "").lower()
        self._voiced = tts in ("gtts", "recorder")
        if tts == "gtts":
            from manim_voiceover.services.gtts import GTTSService

            self.set_speech_service(GTTSService(lang="iw"))
        elif tts == "recorder":
            from manim_voiceover.services.recorder import RecorderService

            self.set_speech_service(RecorderService())

    # -------------------------------------------------------------- text and captions
    def caption(self, text: str) -> Mobject:
        bar = Rectangle(
            width=config.frame_width,
            height=1.05,
            fill_color="#000000",
            fill_opacity=0.55,
            stroke_width=0,
        )
        bar.to_edge(DOWN, buff=0)
        t = he(text, size=22)
        if t.width > config.frame_width - 0.8:
            t.scale_to_fit_width(config.frame_width - 0.8)
        t.move_to(bar)
        return VGroup(bar, t)

    def say(self, text: str, *anims: Animation, min_time: float = 0.0) -> None:
        """Show `text` as a caption (and speak it if a speech service is set) while `anims`
        play; the step lasts at least as long as reading/speaking the text."""
        start = self.renderer.time
        anims = tuple(
            prepare_animation(a) for a in anims
        )  # `x.animate…` builders → Animation
        new = self.caption(text)
        swap = [FadeIn(new, run_time=0.3)]
        if self._caption is not None:
            swap.append(FadeOut(self._caption, run_time=0.3))
        self.play(*swap)
        self._caption = new
        words = len(text.split())
        read = max(2.0, words / 2.4, min_time)
        if self._voiced:
            with self.voiceover(text=text) as tracker:
                if anims:
                    self.play(*anims, run_time=max(tracker.duration, 0.5))
                else:
                    self.wait(tracker.duration)
        else:
            if anims:
                anim_time = max(a.run_time for a in anims)
                self.play(*anims, run_time=max(anim_time, 0.5))
                rest = read - max(anim_time, 0.5)
                if rest > 0.05:
                    self.wait(rest)
            else:
                self.play(Wait(read))
        self._cues.append((start, self.renderer.time, text))

    def heading(self, text: str, sub: str = "") -> VGroup:
        h = (
            he(text, size=36, weight="BOLD")
            .to_edge(UP, buff=0.35)
            .to_edge(RIGHT, buff=0.5)
        )
        g = VGroup(h)
        if sub:
            s = (
                he(sub, size=18, color=INK2)
                .next_to(h, DOWN, buff=0.12)
                .align_to(h, RIGHT)
            )
            g.add(s)
        return g

    def tear_down(self) -> None:
        super().tear_down()
        OUT.mkdir(parents=True, exist_ok=True)
        name = type(self).__name__
        vtt = ["WEBVTT", ""]
        for i, (a, b, t) in enumerate(self._cues, 1):
            vtt += [str(i), f"{_vtt_time(a)} --> {_vtt_time(b)}", "\u200f" + t, ""]
        (OUT / f"{name}.vtt").write_text("\n".join(vtt), encoding="utf-8")
        (OUT / f"{name}.json").write_text(
            json.dumps(
                {
                    "title": self.title_he,
                    "cues": [
                        {"start": a, "end": b, "text": t} for a, b, t in self._cues
                    ],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )


def legend(items: list[tuple[str, str]], size: float = 18) -> VGroup:
    """Right-aligned legend rows: (colour, Hebrew label)."""
    rows = VGroup()
    for color, label in items:
        sw = Rectangle(
            width=0.35, height=0.08, fill_color=color, fill_opacity=1, stroke_width=0
        )
        t = he(label, size=size, color=INK)
        rows.add(VGroup(t, sw).arrange(RIGHT, buff=0.15))
    rows.arrange(DOWN, aligned_edge=RIGHT, buff=0.12)
    return rows


__all__ = [
    "ACCENT",
    "BG",
    "DOWN",
    "INK",
    "INK2",
    "LEFT",
    "MEAS",
    "PH",
    "RIGHT",
    "SIM",
    "THEORY",
    "UP",
    "LabScene",
    "data",
    "he",
    "iso",
    "labeled",
    "legend",
    "mt",
]
