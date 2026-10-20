"""Word export of a report: Hebrew RTL, David 11, line spacing 1.15, 8 pt after, the report's
tables, the automatic explanations, and a MATLAB appendix that redraws the curves."""

from __future__ import annotations

import io

from docx import Document
from docx.oxml.ns import qn
from fastapi.testclient import TestClient


def test_docx_export(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "דו״ח", "experiment_id": "synchronous"}
    ).json()["id"]
    sid = client.post(
        f"/api/projects/{pid}/datasets/synchronous_2025/import",
        json={"study_kind": "short_circuit"},
    ).json()["sets"][0]["id"]
    run = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "ניסוי 3 — קצרים",
            "sections": [{"study_kind": "short_circuit", "run_id": run["id"], "set_id": sid}],
            "student_discussion": "הזרמים גבוהים פי 1.8 מהמודל.",
        },
    )
    assert rep.status_code == 201, rep.text
    r = client.get(f"/api/reports/{rep.json()['id']}/docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    doc = Document(io.BytesIO(r.content))
    normal = doc.styles["Normal"]
    assert normal.font.name == "David" and normal.font.size.pt == 11
    assert normal.paragraph_format.line_spacing == 1.15
    assert normal.paragraph_format.space_after.pt == 8
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ניסוי 3 — קצרים" in text and "הזרמים גבוהים פי 1.8" in text
    assert "הסברים אפשריים לפערים" in text  # the comparison's diagnosis is in the report
    assert "נספח א׳ — קוד MATLAB" in text and "plot(x_sim, y_sim" in text
    assert "x_meas" in text  # measured points are drawn too
    # right-to-left paragraphs and tables
    rtl = [
        p
        for p in doc.paragraphs
        if p._p.pPr is not None and p._p.pPr.find(qn("w:bidi")) is not None
    ]
    assert len(rtl) > 10
    assert doc.tables and doc.tables[0]._tbl.tblPr.find(qn("w:bidiVisual")) is not None
    assert len(doc.tables) >= 4  # spec, simulation, measurements, comparison
