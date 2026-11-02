"""The connection diagram drawn by the app goes into the report as a figure, in HTML and Word.
It is user-supplied, so only a real PNG is accepted."""

from __future__ import annotations

import base64
import io
import struct
import zlib

from docx import Document
from fastapi.testclient import TestClient


def _png(w: int = 4, h: int = 3) -> str:
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode()


def _setup(client: TestClient) -> tuple[str, str]:
    pid = client.post(
        "/api/projects", json={"name": "מעגל", "experiment_id": "synchronous"}
    ).json()["id"]
    sid = client.post(
        f"/api/projects/{pid}/datasets/synchronous_2025/import",
        json={"study_kind": "short_circuit"},
    ).json()["sets"][0]["id"]
    return pid, sid


def test_circuit_figure_in_html_and_docx(client: TestClient) -> None:
    pid, sid = _setup(client)
    png = _png()
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "עם מעגל",
            "sections": [{"study_kind": "short_circuit", "set_id": sid, "circuit_png": png}],
        },
    )
    assert rep.status_code == 201, rep.text
    rid = rep.json()["id"]
    html = client.get(f"/api/reports/{rid}/html").text
    assert f"data:image/png;base64,{png}" in html and "מעגל הניסוי" in html
    doc = Document(io.BytesIO(client.get(f"/api/reports/{rid}/docx").content))
    assert len(doc.inline_shapes) >= 1
    assert any("מעגל הניסוי" in p.text for p in doc.paragraphs)


def test_circuit_figure_rejects_non_png(client: TestClient) -> None:
    pid, sid = _setup(client)
    for bad in ("not base64!!", base64.b64encode(b"GIF89a....").decode()):
        r = client.post(
            f"/api/projects/{pid}/reports",
            json={
                "title": "x",
                "sections": [{"study_kind": "short_circuit", "set_id": sid, "circuit_png": bad}],
            },
        )
        assert r.status_code == 422 and r.json()["error"]["code"] == "bad_diagram", r.text
