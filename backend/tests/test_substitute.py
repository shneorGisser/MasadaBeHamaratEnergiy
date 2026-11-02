"""The report's 'formula → numbers' matches the app's (frontend substitute.test.ts cases)."""

from vel.services.substitute import fmt, substitute, worked


def test_substitution_cases_match_the_app() -> None:
    assert substitute("100·U_k(I_n) / U_1n", {"U_k": 20, "U_k(I_n)": 20.27, "U_1n": 380}) == (
        "100·20.27 / 380.0"
    )
    assert substitute("P0 / (√3·U_L·I0)", {"P0": 60, "U_L": 380, "I0": 0.36}) == (
        "60.00 / (√3·380.0·0.3600)"
    )
    assert substitute("√(Y_m² − g_m²)", {"Y_m": 0.001641, "g_m": 0.0004155}) == (
        "√(0.001641² − (4.155e-4)²)"
    )
    assert substitute("Y0 + Y01", {"Y0": 2}) == "2.000 + Y01"
    assert substitute("3·x²", {"x": -2}) == "3·(-2.000)²"
    assert substitute("a / b", {}) is None


def test_fmt_matches_the_app() -> None:
    assert [fmt(v) for v in (2397.6, 0.36, 4.1709e-4, -2, 0)] == [
        "2398",
        "0.3600",
        "4.171e-4",
        "-2.000",
        "0",
    ]


def test_worked_line() -> None:
    p = {
        "formula": "P0 / U_L²",
        "inputs": {"P0": 60.23, "U_L": 380.0},
        "value": 4.171e-4,
        "unit": "S",
    }
    assert worked(p) == "P0 / U_L²\n= 60.23 / 380.0² = 4.171e-4 S"
    assert worked({"formula": "x", "value": 1}) == "x"
