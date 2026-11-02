"""Explanation videos of the energy-conversion lab (Manim Community, MIT).

Five scenes, one per core idea of the course. Every model curve comes from videos/data.json,
which scripts/video_data.py computes with the app's own studies; every measured point is a
real reading from vel.labdata. The only physics computed here is the textbook definition being
explained (the sum of three phase MMFs, slip from speed), never a result the app also computes.

Render (from the repository root):
    .venv/bin/manim -qm videos/scenes.py RotatingField      # one scene, 720p
    .venv/bin/python videos/render_all.py                     # all, into frontend/public/videos
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from manim import (
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    Arrow,
    Axes,
    Circle,
    Create,
    DashedLine,
    Dot,
    FadeIn,
    FadeOut,
    Line,
    Rectangle,
    Transform,
    ValueTracker,
    VGroup,
    always_redraw,
    linear,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itertools

from common import (
    ACCENT,
    INK,
    INK2,
    MEAS,
    PH,
    SIM,
    THEORY,
    LabScene,
    data,
    he,
    labeled,
    legend,
    mt,
)

D = data()


def num(v: float, digits: int = 3) -> str:
    return f"{v:.{digits}g}"


def axes(x_range: list[float], y_range: list[float], w: float, h: float) -> Axes:
    return Axes(
        x_range=x_range,
        y_range=y_range,
        x_length=w,
        y_length=h,
        axis_config={
            "color": INK2,
            "stroke_width": 2,
            "include_tip": False,
            "font_size": 20,
        },
        tips=False,
    ).add_coordinates(font_size=18)


def curve(
    ax: Axes, pts: list[tuple[float, float]], color: str, width: float = 4
) -> VGroup:
    path = VGroup()
    p = [ax.c2p(x, y) for x, y in pts]
    for a, b in itertools.pairwise(p):
        path.add(Line(a, b, color=color, stroke_width=width))
    return path


def marks(ax: Axes, pts: list[tuple[float, float]], color: str) -> VGroup:
    """Measured points: hollow circles (shape + colour, so they read without colour too)."""
    return VGroup(
        *[
            Circle(radius=0.07, color=color, stroke_width=3).move_to(ax.c2p(x, y))
            for x, y in pts
        ]
    )


# ============================================================================ 1
class RotatingField(LabScene):
    """Three stationary windings, three currents 120° apart → one field of constant size that
    turns at n_s = 60·f/p. The rotor follows, a little slower: the slip."""

    title_he = "השדה המגנטי המסתובב"

    def construct(self) -> None:
        self.add(
            self.heading(self.title_he, "למה מנוע השראה מסתובב בלי שום חיבור לרוטור")
        )
        t = ValueTracker(0.0)  # electrical angle ωt [rad]
        c = LEFT * 3.2 + DOWN * 0.3
        r = 2.0
        stator = Circle(radius=r + 0.25, color=INK2, stroke_width=3).move_to(c)
        axes_lines = VGroup()
        for k in range(3):
            ang = k * 2 * math.pi / 3
            d = np.array([math.cos(ang), math.sin(ang), 0])
            axes_lines.add(
                DashedLine(
                    c - d * (r + 0.25),
                    c + d * (r + 0.25),
                    color=PH[k],
                    stroke_width=2,
                    dash_length=0.12,
                )
            )
        labels = VGroup(
            *[
                he(n, 22, PH[k]).move_to(
                    c
                    + 2.75
                    * np.array(
                        [
                            math.cos(k * 2 * math.pi / 3),
                            math.sin(k * 2 * math.pi / 3),
                            0,
                        ]
                    )
                )
                for k, n in enumerate(("a", "b", "c"))
            ]
        )
        self.say(
            "שלושה ליפופים קבועים בסטטור, מוזזים זה מזה ב-120 מעלות במרחב.",
            Create(stator),
            Create(axes_lines),
            FadeIn(labels),
        )

        def phase_vec(k: int) -> Arrow:
            ang = k * 2 * math.pi / 3
            i = math.cos(t.get_value() - k * 2 * math.pi / 3)
            d = np.array([math.cos(ang), math.sin(ang), 0])
            return Arrow(
                c,
                c + d * i * r * 0.62,
                buff=0,
                color=PH[k],
                stroke_width=5,
                max_tip_length_to_length_ratio=0.18,
            )

        vecs = [always_redraw(lambda k=k: phase_vec(k)) for k in range(3)]

        def total() -> Arrow:
            z = sum(
                math.cos(t.get_value() - k * 2 * math.pi / 3)
                * complex(math.cos(k * 2 * math.pi / 3), math.sin(k * 2 * math.pi / 3))
                for k in range(3)
            )
            return Arrow(
                c,
                c + np.array([z.real, z.imag, 0]) * r * 0.62,
                buff=0,
                color=INK,
                stroke_width=8,
                max_tip_length_to_length_ratio=0.14,
            )

        tot = always_redraw(total)

        # the three currents in time, with the moving instant (the "time scrubber")
        ax = axes([0, 2 * math.pi, math.pi / 2], [-1.2, 1.2, 1], 5.2, 2.6).move_to(
            RIGHT * 3.4 + UP * 0.6
        )
        ax.coordinate_labels.set_opacity(0)
        waves = VGroup(
            *[
                ax.plot(
                    lambda x, k=k: math.cos(x - k * 2 * math.pi / 3),
                    color=PH[k],
                    stroke_width=3,
                )
                for k in range(3)
            ]
        )
        cursor = always_redraw(
            lambda: Line(
                ax.c2p(t.get_value() % (2 * math.pi), -1.2),
                ax.c2p(t.get_value() % (2 * math.pi), 1.2),
                color=ACCENT,
                stroke_width=3,
            )
        )
        dots = [
            always_redraw(
                lambda k=k: Dot(
                    ax.c2p(
                        t.get_value() % (2 * math.pi),
                        math.cos(t.get_value() - k * 2 * math.pi / 3),
                    ),
                    color=PH[k],
                    radius=0.07,
                )
            )
            for k in range(3)
        ]
        wlabel = labeled(
            "זרמי הפאזות לאורך מחזור אחד:", r"i_a,\ i_b,\ i_c", 24
        ).next_to(ax, UP, buff=0.15)
        self.say(
            "בליפופים זורמים שלושה זרמים סינוסיים, מוזזים ב-120 מעלות בזמן.",
            Create(ax),
            Create(waves),
            FadeIn(wlabel),
        )
        self.add(cursor, *dots)
        self.say(
            "כל ליפוף יוצר שדה לאורך הציר שלו בלבד, וגודלו עולה ויורד עם הזרם שלו.",
            *[FadeIn(v) for v in vecs],
        )
        self.add(*vecs)
        self.say(
            "בכל רגע מחברים את שלושת החצים. ננוע בזמן ונראה מה קורה לסכום.",
            t.animate(run_time=3).set_value(math.pi / 3),
        )
        self.add(tot)
        self.say(
            "הסכום, החץ הלבן, הוא שדה באורך קבוע שמסתובב. אורכו פי 1.5 מהשיא של פאזה בודדת.",
            t.animate(rate_func=linear, run_time=6).set_value(
                math.pi / 3 + 2 * math.pi
            ),
        )
        f = mt(
            r"\vec F(t)=\vec F_a+\vec F_b+\vec F_c=\tfrac{3}{2}F_m\,e^{j\omega t}",
            32,
            ACCENT,
        ).move_to(RIGHT * 3.4 + DOWN * 1.15)
        self.say(
            "זו התוצאה המתמטית: סיבוב אחיד, בלי שום חלק נע בסטטור.",
            FadeIn(f),
            t.animate(rate_func=linear, run_time=5).set_value(
                math.pi / 3 + 4 * math.pi
            ),
        )
        ns = labeled(
            "מהירות סינכרונית:",
            r"n_s=\frac{60f}{p}=\frac{60\cdot 50}{2}=1500\ \mathrm{rpm}",
            30,
        ).next_to(f, DOWN, buff=0.25)
        self.say(
            "במנוע של 4 קטבים (2 זוגות) השדה משלים סיבוב בכל שני מחזורים: 1500 סל״ד ב-50 הרץ.",
            FadeIn(ns),
        )
        m = D["induction"]["measured_load"][0]
        s = (1500 - m["n"]) / 1500
        slip = labeled(
            "החלקה:",
            rf"s=\frac{{n_s-n}}{{n_s}}=\frac{{1500-{m['n']:g}}}{{1500}}={100 * s:.1f}\%",
            30,
            MEAS,
        )
        slip.move_to(
            f
        )  # replaces the MMF formula: the caption bar needs the room below
        self.say(
            f"הרוטור לא מגיע לסנכרון. בדף המדידות שלכם, במומנט {m['M']:g} ניוטון-מטר, נמדדו {m['n']:g} סל״ד.",
            FadeOut(f),
            FadeIn(slip),
        )
        self.say(
            "אילו הרוטור היה מסתובב בדיוק עם השדה, לא היה שינוי שטף דרכו, לא היה מתח מושרה, לא זרם ולא מומנט. ההחלקה היא המחיר של המומנט.",
            t.animate(rate_func=linear, run_time=8).set_value(
                math.pi / 3 + 6 * math.pi
            ),
        )


# ============================================================================ 2
class TorqueSpeed(LabScene):
    """The equivalent circuit, the torque–speed curve of the fitted AP-3030, the lab's load
    points on it, and the breakdown (Kloss) parameters."""

    title_he = "אופיין מומנט–מהירות של מנוע ההשראה"

    def construct(self) -> None:
        im = D["induction"]
        self.add(
            self.heading(self.title_he, "מעגל התמורה, המומנט, ונקודות העומס שמדדתם")
        )
        e = im["ecm"]
        box = (
            VGroup(
                he("מעגל תמורה לפאזה (ליפוף במשולש)", 20, INK2),
                mt(rf"R_1={e['R1']:g}\,\Omega\quad X_1={e['X1']:g}\,\Omega", 28),
                mt(rf"R_2'={e['R2p']:g}\,\Omega\quad X_2'={e['X2p']:g}\,\Omega", 28),
                mt(
                    rf"X_m={e['Xm']:g}\,\Omega\quad R_{{fe}}={e['R_fe'] / 1000:.1f}\,\mathrm{{k}}\Omega",
                    28,
                ),
            )
            .arrange(DOWN, aligned_edge=RIGHT, buff=0.18)
            .to_edge(RIGHT, buff=0.6)
            .shift(UP * 1.0)
        )
        self.say(
            "המנוע הוא שנאי מסתובב. ההתנגדות R2′ חלקי s מייצגת גם את הפסדי הרוטור וגם את ההספק המכני.",
            FadeIn(box),
        )
        formula = mt(
            r"P_{ag}=3I_2'^2\frac{R_2'}{s},\quad P_{cu2}=s\,P_{ag},\quad M=\frac{P_{ag}}{\omega_s}",
            30,
            ACCENT,
        )
        formula.next_to(box, DOWN, buff=0.4).align_to(box, RIGHT)
        self.say(
            "ההספק שעובר במרווח האוויר מתחלק: החלק s נשרף בנחושת של הרוטור, והשאר הופך לעבודה מכנית.",
            FadeIn(formula),
        )
        ts = im["torque_speed"]
        mmax = max(r["M_em"] for r in ts)
        ax = (
            axes([0, 1500, 300], [0, math.ceil(mmax + 0.5), 1], 6.0, 3.3)
            .to_edge(LEFT, buff=0.7)
            .shift(DOWN * 0.2)
        )
        xl = mt(r"n\ [\mathrm{rpm}]", 24, INK2).next_to(ax.x_axis, DOWN, buff=0.35)
        yl = mt(r"M\ [\mathrm{N\,m}]", 24, INK2).next_to(ax.y_axis, UP, buff=0.1)
        model = curve(ax, [(r["n"], r["M_em"]) for r in ts], SIM)
        self.say(
            "זה המומנט שהמודל המכויל מחשב בכל מהירות, מעמידה ועד סנכרון.",
            Create(ax),
            FadeIn(xl),
            FadeIn(yl),
            Create(model, run_time=3),
        )
        p = im["parameters"]
        top = max(ts, key=lambda r: r["M_em"])  # the breakdown point of the curve drawn
        peak = Dot(ax.c2p(top["n"], top["M_em"]), color=ACCENT, radius=0.08)
        pk = mt(
            rf"M_{{max}}={top['M_em']:.2f}\ \mathrm{{N\,m}},\ s={top['slip']:.2f}",
            26,
            ACCENT,
        ).next_to(peak, UP, buff=0.15)
        st = Dot(ax.c2p(0, p["M_start"]), color=ACCENT, radius=0.08)
        stl = (
            labeled(
                "התנעה:", rf"M_{{st}}={p['M_start']:.2f}\ \mathrm{{N\,m}}", 26, ACCENT
            )
            .next_to(st, RIGHT, buff=0.25)
            .shift(DOWN * 0.4)
        )  # below the rising curve
        self.say(
            "שתי נקודות מאפיינות: מומנט ההתנעה בעמידה, ומומנט הפריצה, המקסימום. מימין לו הפעולה יציבה.",
            FadeIn(peak),
            FadeIn(pk),
            FadeIn(st),
            FadeIn(stl),
        )
        kl = (
            labeled(
                "קלוס:", r"\frac{M}{M_{max}}=\frac{2}{s/s_{cr}+s_{cr}/s}", 30, THEORY
            )
            .next_to(formula, DOWN, buff=0.3)
            .align_to(formula, RIGHT)
        )
        kloss = curve(ax, [(r["n"], r["M_kloss"]) for r in ts], THEORY, width=3)
        kloss.set_stroke(opacity=0.9)
        self.say(
            f"נוסחת קלוס היא קירוב שמזניח את R1, עם שיא של {p['M_max']:.2f} ניוטון-מטר. כאן היא נמוכה מהמודל המלא, כי R1 של המנוע הקטן גדול.",
            FadeIn(kl),
            Create(kloss, run_time=2),
        )
        meas = marks(ax, [(m["n"], m["M"]) for m in im["measured_load"]], MEAS)
        self.say(
            "והעיגולים הם הקריאות שלכם מבלם האבקה. הם יושבים על הענף היציב, בין 1310 ל-1450 סל״ד.",
            FadeIn(meas),
        )
        lg = (
            legend([(SIM, "מודל מכויל"), (THEORY, "קלוס"), (MEAS, "מדידות 2026")])
            # inside the plot, under the curve: empty there, and the caption bar stays free
            .move_to(ax.c2p(800, 0.75))
        )
        self.add(lg)
        self.say(
            f"ובכנות: המומנט הנקוב לפי השלט הוא {p['M_n']:.2f} ניוטון-מטר, כמעט כמו מומנט הפריצה של המודל. השלט והדף לא מתיישבים, וזה מתועד בפרויקט.",
            min_time=6,
        )


# ============================================================================ 3
class TransformerTests(LabScene):
    """No-load test → magnetising branch; short-circuit test → series impedance."""

    title_he = "בדיקת ריקם ובדיקת קצר בשנאי"

    def construct(self) -> None:
        tr = D["transformer"]
        self.add(
            self.heading(self.title_he, "שתי מדידות פשוטות שחושפות את כל מעגל התמורה")
        )
        why = (
            VGroup(
                he("ריקם: מתח נקוב, משני פתוח", 24, SIM),
                he("כמעט כל הזרם הוא זרם מגנוט: נותן את הענף המקבילי", 20, INK2),
                he("קצר: משני מקוצר, מתח נמוך עד זרם נקוב", 24, MEAS),
                he("השטף קטן, הפסדי הברזל זניחים: נותן את העכבה הטורית", 20, INK2),
            )
            .arrange(DOWN, aligned_edge=RIGHT, buff=0.22)
            .to_edge(RIGHT, buff=0.6)
            .shift(UP * 0.8)
        )
        self.say(
            "כל בדיקה מבודדת חצי אחד של מעגל התמורה, כי בכל אחת החצי השני כמעט לא משפיע.",
            FadeIn(why, lag_ratio=0.3, run_time=3),
        )
        nl = tr["no_load"]
        u_max = max(r["U1L"] for r in nl)
        i_max = max(r["I0"] for r in nl)
        ax = (
            axes(
                [0, math.ceil(u_max / 100) * 100, 100],
                [0, round(i_max * 1.25, 3), round(i_max * 1.25 / 4, 3)],
                5.6,
                3.2,
            )
            .to_edge(LEFT, buff=0.8)
            .shift(DOWN * 0.2)
        )
        xl = labeled("קווי", r"U_1\ [\mathrm{V}]", 24).next_to(
            ax.x_axis, DOWN, buff=0.35
        )
        yl = mt(r"I_0\ [\mathrm{A}]", 24, INK2).next_to(ax.y_axis, UP, buff=0.1)
        c0 = curve(ax, [(r["U1L"], r["I0"]) for r in nl], SIM)
        self.say(
            "בריקם, זרם המגנוט גדל לינארית עם המתח, ואז מתעקם כלפי מעלה. זו הרוויה של הליבה.",
            Create(ax),
            FadeIn(xl),
            FadeIn(yl),
            Create(c0, run_time=3),
        )
        pn = tr["no_load_parameters"]
        f1 = mt(
            rf"\cos\varphi_0=\frac{{P_0}}{{\sqrt3\,U\,I_0}}={pn['cos_phi0']:.2f}",
            30,
            ACCENT,
        )
        f2 = mt(
            rf"R_{{fe}}={pn['R_fe'] / 1000:.1f}\,\mathrm{{k}}\Omega,\quad X_m={pn['X_m'] / 1000:.2f}\,\mathrm{{k}}\Omega",
            30,
            ACCENT,
        )
        g = (
            VGroup(f1, f2)
            .arrange(DOWN, aligned_edge=RIGHT, buff=0.15)
            .next_to(why, DOWN, buff=0.4)
            .align_to(why, RIGHT)
        )
        self.say(
            "מקדם ההספק בריקם נמוך, כ-0.2: רוב הזרם מגנוטי, ורק חלק קטן מכסה את הפסדי הברזל.",
            FadeIn(g),
        )
        self.play(FadeOut(VGroup(ax, xl, yl, c0)))
        sc = tr["short_circuit"]
        # the 2025 table recorded the PHASE voltage (docs/lab-data-2025.md): plot phase volts
        pts = [(r["I1k"], r["U_k"] / math.sqrt(3)) for r in sc]
        ax2 = (
            axes([0, 0.4, 0.1], [0, 25, 5], 5.6, 3.2)
            .to_edge(LEFT, buff=0.8)
            .shift(DOWN * 0.2)
        )
        xl2 = mt(r"I_k\ [\mathrm{A}]", 24, INK2).next_to(ax2.x_axis, DOWN, buff=0.35)
        yl2 = labeled("פאזי", r"U_k\ [\mathrm{V}]", 24).next_to(
            ax2.y_axis, UP, buff=0.1
        )
        c1 = curve(ax2, pts, SIM)
        self.say(
            "בקצר, המתח הדרוש לזרם הנקוב קטן, כמה אחוזים מהנקוב, והקשר לינארי לגמרי: אין רוויה בשטף כל כך קטן.",
            Create(ax2),
            FadeIn(xl2),
            FadeIn(yl2),
            Create(c1, run_time=2),
        )
        ms = marks(
            ax2, [(m["I1k"], m["U_k"]) for m in tr["measured_short_circuit"]], MEAS
        )
        self.say("העיגולים הם טבלת 2025 שהועתקה מהדוח. הם על הקו של המודל.", FadeIn(ms))
        ps = tr["short_circuit_parameters"]
        f3 = mt(
            rf"Z_k=\frac{{U_k}}{{I_k}}={ps['Z_k']:.1f}\,\Omega,\quad \cos\varphi_k={ps['cos_phik']:.2f}",
            30,
            ACCENT,
        )
        f4 = mt(
            rf"R_k={ps['r_k']:.1f}\,\Omega,\quad X_k={ps['x_k']:.1f}\,\Omega,\quad u_k={ps['u_k_pct']:.1f}\%",
            30,
            ACCENT,
        )
        g2 = VGroup(f3, f4).arrange(DOWN, aligned_edge=RIGHT, buff=0.15)
        g2.scale_to_fit_width(min(g2.width, why.width + 0.4))
        g2.move_to(g).align_to(why, RIGHT)
        self.say(
            "מהשיפוע מקבלים את עכבת הקצר, ומהספק הקצר את החלק ההתנגדותי. שתי בדיקות, ארבעה פרמטרים.",
            Transform(g, g2),
        )
        self.say(
            "ושימו לב לבחירה בין מתח קווי לפאזי. בדוח 2025 נרשם מתח פאזי בעמודה שמצפה לקווי, וזה ההבדל של שורש 3.",
            min_time=5,
        )


# ============================================================================ 4
class SyncOccScc(LabScene):
    """Open-circuit and short-circuit characteristics → synchronous reactance and SCR."""

    title_he = "אופייני ריקם וקצר של המכונה הסינכרונית"

    def construct(self) -> None:
        s = D["synchronous"]
        self.add(
            self.heading(
                self.title_he, "איך שני גרפים נותנים את הריאקטנס הסינכרוני X_s"
            )
        )
        occ = s["occ"]
        ax = (
            axes([0, 2.5, 0.5], [0, 400, 100], 6.2, 3.3)
            .to_edge(LEFT, buff=0.8)
            .shift(DOWN * 0.2)
        )
        xl = mt(r"I_f\ [\mathrm{A}]", 24, INK2).next_to(ax.x_axis, DOWN, buff=0.35)
        yl = labeled("פאזי", r"E_f\ [\mathrm{V}]", 24).next_to(ax.y_axis, UP, buff=0.1)
        c = curve(ax, [(r["If"], r["Ef"]) for r in occ], SIM)
        self.say(
            "בריקם, הרוטור מסתובב בסנכרון וזרם העירור עולה. המתח המושרה עוקב אחרי השטף.",
            Create(ax),
            FadeIn(xl),
            FadeIn(yl),
            Create(c, run_time=3),
        )
        meas = marks(ax, [(m["If"], m["Ef_up"]) for m in s["measured_occ"]], MEAS)
        self.say(
            "בהתחלה הקשר לינארי, קו מרווח האוויר. אחר כך הברזל נכנס לרוויה והעקומה מתכופפת. העיגולים הם המדידות שלכם מ-2026.",
            FadeIn(meas),
        )
        f1 = (
            mt(r"E_f=k\,\Phi(I_f)\,n", 34, ACCENT)
            .to_edge(RIGHT, buff=0.7)
            .shift(UP * 1.2)
        )
        self.say(
            "המתח פרופורציוני לשטף ולמהירות. במהירות קבועה, הגרף הוא בעצם עקומת המגנוט של המכונה.",
            FadeIn(f1),
        )
        ax2 = axes([0, 2.5, 0.5], [0, 0.6, 0.2], 6.2, 3.3).move_to(ax)
        yl2 = mt(r"I_k\ [\mathrm{A}]", 24, INK2).next_to(ax2.y_axis, UP, buff=0.1)
        scc = curve(ax2, [(r["If"], r["Ik3"]) for r in s["scc"]], THEORY)
        ms = marks(ax2, [(m["If"], m["Ik3"]) for m in s["measured_scc"]], MEAS)
        self.say(
            "בקצר תלת-פאזי, זרם הסטטור לינארי בזרם העירור. השדה של הזרם מבטל כמעט את כל שדה הרוטור, ולכן הברזל לא רווי.",
            FadeOut(VGroup(c, meas, yl)),
            Transform(ax, ax2),
            FadeIn(yl2),
            Create(scc, run_time=2),
            FadeIn(ms),
        )
        p = s["scc_parameters"]
        f2 = (
            mt(r"X_s=\frac{E_f(I_f)}{I_k(I_f)}", 34, ACCENT)
            .next_to(f1, DOWN, buff=0.35)
            .align_to(f1, RIGHT)
        )
        f3 = (
            mt(
                rf"X_s={p['Xs']:.0f}\,\Omega={p['Xs_pu']:.2f}\ \mathrm{{pu}}",
                34,
                ACCENT,
            )
            .next_to(f2, DOWN, buff=0.25)
            .align_to(f1, RIGHT)
        )
        self.say(
            "באותו זרם עירור, מחלקים את מתח הריקם בזרם הקצר. התוצאה היא הריאקטנס הסינכרוני, בחלק הלינארי.",
            FadeIn(f2),
            FadeIn(f3),
        )
        f4 = (
            mt(r"\mathrm{SCR}=1/X_{s,\mathrm{pu}}", 32, INK)
            .next_to(f3, DOWN, buff=0.25)
            .align_to(f1, RIGHT)
        )
        self.say(
            f"ובערכים יחסיים הריאקטנס גדול מ-1: זרם הקצר המתמשך קטן מהזרם הנקוב. יחס הקצר הוא בערך {1 / p['Xs_pu']:.2f}.",
            FadeIn(f4),
        )
        self.say(
            "ושימו לב לשתי הנקודות האחרונות בטבלת הקצר שלכם: הן חורגות מהקו, וגם מהיחס לקצר הדו-פאזי שנמדד באותה שורה. כנראה טעות קריאה, ובדיוק מה שכדאי לבדוק לפני שמפרקים את המעגל.",
            min_time=6,
        )


# ============================================================================ 5
class VCurves(LabScene):
    """Armature current vs field current at constant real power: the V-curves."""

    title_he = "עקומות V של המכונה הסינכרונית"

    def construct(self) -> None:
        s = D["synchronous"]
        self.add(
            self.heading(
                self.title_he, "זרם העירור קובע את ההספק הריאקטיבי, לא את הפעיל"
            )
        )
        rows = [r for r in s["v_curves"] if r["state"] == "סינכרוני"]
        imax = max(r["Ia"] for r in rows)
        ax = (
            axes([1, 6.5, 1], [0, round(imax * 1.15, 1), 0.2], 6.4, 3.4)
            .to_edge(LEFT, buff=0.8)
            .shift(DOWN * 0.2)
        )
        xl = mt(r"I_f\ [\mathrm{A}]", 24, INK2).next_to(ax.x_axis, DOWN, buff=0.35)
        yl = mt(r"I_a\ [\mathrm{A}]", 24, INK2).next_to(ax.y_axis, UP, buff=0.1)
        self.say(
            "המכונה מחוברת לרשת. ההספק הפעיל קבוע לפי המומנט על הציר, ורק זרם העירור משתנה.",
            Create(ax),
            FadeIn(xl),
            FadeIn(yl),
        )
        colors = {0.0: SIM, 100.0: THEORY, 200.0: ACCENT}
        curves = VGroup()
        for pset, col in colors.items():
            pts = sorted((r["If"], r["Ia"]) for r in rows if r["P_set"] == pset)
            curves.add(curve(ax, pts, col))
        self.say(
            "לכל הספק מתקבלת עקומה בצורת V. ככל שההספק גדול יותר, העקומה גבוהה יותר.",
            Create(curves, lag_ratio=0.5, run_time=4),
        )
        lg = (
            legend([(SIM, "P ≈ 0 W"), (THEORY, "P = 100 W"), (ACCENT, "P = 200 W")])
            .to_edge(RIGHT, buff=0.7)
            .shift(UP * 1.4)
        )
        self.add(lg)
        under = (
            he("תת-עירור: צורכת ריאקטיבי (השראי)", 22, INK)
            .next_to(lg, DOWN, buff=0.45)
            .align_to(lg, RIGHT)
        )
        over = (
            he("על-עירור: מספקת ריאקטיבי (קיבולי)", 22, INK)
            .next_to(under, DOWN, buff=0.2)
            .align_to(lg, RIGHT)
        )
        bottom = (
            labeled("בתחתית ה-V:", r"\cos\varphi=1", 30, ACCENT, ACCENT)
            .next_to(over, DOWN, buff=0.2)
            .align_to(lg, RIGHT)
        )
        self.say(
            "משמאל לתחתית המכונה בתת-עירור וצורכת הספק ריאקטיבי. מימין, בעל-עירור, היא מספקת אותו לרשת כמו קבל.",
            FadeIn(under),
            FadeIn(over),
        )
        self.say(
            "בתחתית כל V הזרם מינימלי ומקדם ההספק 1. כל הזרם עושה עבודה.",
            FadeIn(bottom),
        )
        f = (
            mt(r"P=\frac{3\,U\,E_f\sin\delta}{X_s}", 34, ACCENT)
            .next_to(bottom, DOWN, buff=0.4)
            .align_to(lg, RIGHT)
        )
        self.say(
            "למה ההספק הפעיל לא משתנה? כשמעלים את מתח העירור, זווית העומס קטנה בדיוק כדי לשמור על אותו הספק.",
            FadeIn(f),
        )
        self.say(
            "בתעשייה זה המפצה הסינכרוני: מכונה ללא עומס על הציר, בעל-עירור, שמשפרת את מקדם ההספק של המפעל.",
            min_time=5,
        )


SCENES = [RotatingField, TorqueSpeed, TransformerTests, SyncOccScc, VCurves]
_ = (ORIGIN, Rectangle)
