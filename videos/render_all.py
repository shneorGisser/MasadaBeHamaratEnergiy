"""Render every explanation video into frontend/public/videos (mp4 + captions + transcript).

Run from the repository root:  .venv/bin/python videos/render_all.py [-ql|-qm|-qh] [Scene …]
Default quality -qm (720p30). The render cache goes to videos/media (git-ignored).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "frontend" / "public" / "videos"
SCENES = ["RotatingField", "TorqueSpeed", "TransformerTests", "SyncOccScc", "VCurves"]
QUALITY = {"-ql": "480p15", "-qm": "720p30", "-qh": "1080p60"}


def main() -> None:
    q = next((a for a in sys.argv[1:] if a in QUALITY), "-qm")
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or SCENES
    OUT.mkdir(parents=True, exist_ok=True)
    manim = Path(sys.executable).with_name("manim")
    for name in names:
        subprocess.run(
            [
                str(manim),
                q,
                "--media_dir",
                str(HERE / "media"),
                str(HERE / "scenes.py"),
                name,
            ],
            check=True,
            env={**__import__("os").environ, "VEL_VIDEO_OUT": str(OUT)},
        )
        mp4 = HERE / "media" / "videos" / "scenes" / QUALITY[q] / f"{name}.mp4"
        shutil.copy(mp4, OUT / f"{name}.mp4")
        # a WebM (VP9) next to the H.264 mp4: open-source Chromium builds and some Linux
        # browsers cannot decode H.264; the page offers both and the browser picks
        webm = OUT / f"{name}.webm"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(mp4),
                "-c:v",
                "libvpx-vp9",
                "-crf",
                "36",
                "-b:v",
                "0",
                "-row-mt",
                "1",
                "-an",
                str(webm),
            ],
            check=True,
        )
        for f in (OUT / f"{name}.mp4", webm):
            print("→", f, f"{f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
