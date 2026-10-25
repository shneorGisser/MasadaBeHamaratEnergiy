"""Report charts: PNGs from the report's tables, Hebrew labels laid out right to left."""

from __future__ import annotations

from vel.services.report_charts import render_curve, visual


def test_hebrew_labels_are_right_to_left_paragraphs() -> None:
    """matplotlib ≥ 3.11 runs the bidi algorithm; a label starting with Latin ("i קו L1") must
    still be a right-to-left paragraph, so it gets a leading RLM. Latin-only labels are kept."""
    assert visual("i קו L1 [A]") == "\u200fi קו L1 [A]"
    assert visual("I_f / I_f0") == "I_f / I_f0"
    import matplotlib

    major, minor = (int(x) for x in matplotlib.__version__.split(".")[:2])
    assert (major, minor) >= (3, 11)


def test_render_curve_is_a_png_with_measured_points() -> None:
    table = {
        "columns": [
            {"key": "x", "label_he": "זרם", "unit": "A"},
            {"key": "y", "label_he": "מתח", "unit": "V"},
        ],
        "rows": [{"x": float(i), "y": 2.0 * i} for i in range(5)],
    }
    png = render_curve({"x": "x", "y": "y", "title_he": "אופיין"}, table, [{"x": 1.0, "y": 2.1}])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000
