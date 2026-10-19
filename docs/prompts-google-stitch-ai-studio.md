# פרומפטים ל-Google Stitch ול-Google AI Studio

## איך שלושת הכלים עובדים יחד בפרויקט הזה

האפליקציה כבר בנויה ועובדת: React עם FastAPI, פותר, בסיס נתונים ו-121 בדיקות (98 backend, 8 יחידה, 15 E2E); שני ניסויים (שנאי, מנוע השראה). לכן תהליך העבודה שונה מבנייה מאפס:

| כלי | תפקיד | מה **לא** לעשות בו |
|---|---|---|
| **Google Stitch** | כיוון ויזואלי: 5–7 מסכים מרכזיים וקובץ `DESIGN.md` (צבעים, גופנים, ריווח, רכיבים) | לא להעתיק את ה-HTML שלו לקוד, כי הוא מייצא HTML/Tailwind ולא React |
| **Google AI Studio** | אב-טיפוס לחיץ של העיצוב החדש לסקירה (Export from Stitch). אופציונלית: ניסויי UI על ענף נפרד מ-GitHub | לא לארח בו את האפליקציה, כי הוא מריץ Node.js בלבד ואין בו Python, FastAPI או פותר |
| **Claude (הסשן הזה)** | מיישם את `DESIGN.md` על רכיבי ה-React הקיימים, שומר על הלוגיקה ועל הבדיקות, ומעלה ל-Cloud Run | — |

**מה להחזיר אליי:** את `DESIGN.md`, צילומי מסך של המסכים שאהבת, ואת ה-zip של ה-HTML (לעיון בלבד). אם תחבר את שרת ה-MCP של Stitch (`https://stitch.googleapis.com/mcp`), אוכל למשוך את העיצוב ישירות. את זה עוד לא בדקתי בחשבון שלך.

**חשוב על RTL:** ל-Stitch אין תמיכה מתועדת בעברית מימין לשמאל. לכן בכל פרומפט יש פסקת "חוזה RTL". אחרי כל מסך צריך לבדוק שהניווט מתחיל מימין ושהחצים הפוכים.
**כללי עבודה (מהמדריך הרשמי של Stitch):** פרומפט ראשון פשוט, ואחר כך שינוי אחד או שניים בכל פרומפט. עדיף לא לעבור 3,000 תווים, כי משתמשים מדווחים שרכיבים נעלמים מעל 5,000. כדאי לצלם כל מצב טוב לפני ששולחים את הפרומפט הבא.

הפרומפטים באנגלית, כי Stitch מגיב אליה הכי טוב. הטקסטים שיופיעו בממשק כתובים בעברית בתוך הפרומפט.

---

## Stitch — פרומפט 0: הקשר וחוזה RTL (מדביקים בתחילת כל פרומפט)

```
CONTEXT: "Virtual Energy Lab" (מעבדה וירטואלית להמרת אנרגיה) — a serious web tool for
electrical-engineering students: simulate a 3-phase transformer experiment, enter real lab
measurements, compare, and produce a lab report. Desktop-first web app, also usable on a tablet.

RTL CONTRACT (mandatory): root has dir="rtl" lang="he". All UI text in Hebrew. Text is
right-aligned. Navigation, sidebars and the logo start on the RIGHT. Directional icons
(back/forward arrows, chevrons) are mirrored. Use logical spacing (ms-/me-, ps-/pe-).
EXCEPTIONS that stay left-to-right: numbers with units (e.g. "380.0 V"), formulas, chart
axes, the circuit schematic canvas and the 3D canvas.

STYLE: precise, technical, trustworthy — like a modern lab instrument, not a game.
Font: "Rubik" or "Assistant" for UI, monospace for numbers. Tabular numerals.
Three semantic source colors used consistently everywhere:
  simulation = blue (#1F6FB2), real measurement = brick red (#A2462E),
  theory/model = olive green (#4B6B2F). Warnings = amber, errors = red.
Light theme first.
```

## Stitch — פרומפט 1: מסך-הבית של הניסוי (קובע את מערכת העיצוב)

```
[paste CONTEXT + RTL CONTRACT]

Design the main experiment workspace screen (web, 1440px wide).
ANATOMY:
- Top bar (right): app name "מעבדה וירטואלית להמרת אנרגיה", project name "קבוצה 3",
  a small amber badge "ערכים מוערכים — לא נתוני שלט".
- Tabs under the header: "ניסויים וסימולציה" (active), "מצב מודרך", "מפרט השנאי", "דו״חות".
- Secondary tabs for the 6 lab tests: "בדיקת בידוד", "התנגדות ליפופים", "ניסוי ריקם" (active),
  "ניסוי קצר", "ניסוי עומס", "קבוצות חיבורים".
- Segmented control: "סימולציה" / "מדידות מעבדה והשוואה".
- Large panel "מעגל הניסוי" = PLACEHOLDER for an interactive circuit schematic (just a framed
  canvas with a small toolbar: "הוסף רכיב", "שמור מעגל", "מחק נבחר"). Do not draw a circuit.
- Panel "תנאי הניסוי": text field "מתחי קו לסוויפ [V]" with value "190, 228, 266, 304, 342, 380, 418, 456",
  and a primary button "הרץ סימולציה".
- Results: status chip "הצליח עם אזהרות", amber warning box, a data table
  "טבלה 1.3 — ריקם" (columns: #, U1 קווי [V], U1 פאזי [V], U2 קווי [V], I0 [A], P0 [W], cos φ0),
  two chart PLACEHOLDERS ("עקומת המגנוט U1 = f(I0)", "הפסדי ריקם P0 = f(U1)").
- Left side: narrow "היסטוריית ריצות" list with status chips.
VIBE: calm, high-contrast, generous whitespace, 8px grid, subtle borders instead of shadows.
```

## Stitch — פרומפטים 2–7 (כל אחד בנפרד, ואחרי כל אחד שינויי המשך קטנים)

**2. רשימת פרויקטים**
```
[CONTEXT + RTL CONTRACT] Using exactly the header, colors, fonts and spacing of the workspace
screen, design the projects home: page title "הפרויקטים שלי", a create form (field "שם הפרויקט",
dropdown "ניסוי", button "צור פרויקט"), a link-style action "שחזור פרויקט מקובץ גיבוי",
and a list of project rows (name, experiment title, "עודכן" date, delete action). Include an empty state.
```

**3. מדידות והשוואה**
```
[CONTEXT + RTL CONTRACT] Same design system. Screen "מדידות מעבדה והשוואה" for the no-load test:
(1) "מדידות אמת מהמעבדה": an editable spreadsheet-like table, each cell = number input + small unit
dropdown (V/mV/kV, A/mA). Empty cells show "חסר" in a dashed amber style. One corrected cell shows
a small badge "תוקן ×1". Footer: "+ שורה", chip "33 ערכים חסרים".
(2) "השוואה: מדידה מול סימולציה": a run selector, a reference selector, a primary button
"סימולציה בנקודות המדידה", a table with columns גודל | נמדד (red) | מסומלץ (blue) |
שגיאה מוחלטת | שגיאה יחסית, and a parameter table מודל (green) | סימולציה | מדידה.
(3) Two chart placeholders with a legend showing the three source colors.
```

**4. שולחן מעבדה תלת-ממדי**
```
[CONTEXT + RTL CONTRACT] Same design system. Screen section "שולחן מעבדה תלת-ממדי": a large 3D
canvas PLACEHOLDER (dark-neutral background, do not render 3D content) with floating instrument
label chips like "A · 0.3623 A" and "V2 · 219.6 V". Above it a control strip: a slider
"וריאק (G): 380.0 V", a checkbox "מפסק S סגור", status chip "הצליח", and an info chip
"נקודת עבודה חיה מהפותר · לא נשמרת".
```

**5. מצב מודרך**
```
[CONTEXT + RTL CONTRACT] Same design system. "מצב מודרך — לפי סדר החוברת": a progress bar "5 / 27",
then a vertical list of step cards. Done steps: green check, muted. The next step: highlighted
with an accent border. Each card: title, 1–2 lines of instruction text, buttons "קראתי" or "עבור".
```

**6. מפרט השנאי**
```
[CONTEXT + RTL CONTRACT] Same design system. Form screen "מפרט השנאי" with three cards:
"נתוני שלט", "מעגל תמורה (לליפוף, Ω)", "בידוד (MΩ)". Numeric inputs are LTR inside RTL labels.
A fourth card "גדלים נגזרים" shows read-only values. A dropdown "טען ערכים מוכנים" and a primary "שמור מפרט".
```

**7. דו״ח**
```
[CONTEXT + RTL CONTRACT] Same design system. Screen "הפקת דו״ח": a table to choose which tests to include
(checkbox, run dropdown, measurement-set dropdown), a large textarea "דיון (נכתב על ידי הסטודנט)",
button "הפק דו״ח", and below it a printable A4 report preview in Hebrew (serif "David"-like font).
```

**שינויי המשך מומלצים (אחד בכל פעם):**
- `Make all primary buttons fully rounded; keep secondary buttons outlined.`
- `Increase table density: 36px rows, sticky header, zebra striping off.`
- `Create a dark theme variant of the workspace screen with the same source colors.`
- `Check RTL: navigation must start on the right; mirror every chevron; keep numbers LTR.`
- בסוף: `Export the design system as DESIGN.md.` (או מתפריט הייצוא)

---

## Google AI Studio — פרומפט 1: אב-טיפוס לסקירה (אחרי "Export to AI Studio" מ-Stitch)

```
Build a clickable PROTOTYPE of the attached Stitch screens for design review only.
Rules:
- Hebrew RTL everywhere (dir="rtl" lang="he"); numbers, units, formulas and charts stay LTR.
- Navigation between: projects → workspace (6 test tabs, simulation/measurement toggle) →
  guided mode → transformer spec → reports.
- NO engineering calculations and NO Gemini calls. All numbers are static placeholders, and every
  screen shows a small fixed banner "אב-טיפוס עיצובי — נתוני דמה, לא תוצאות סימולציה".
- Charts, the circuit canvas and the 3D bench are framed placeholders.
- Keep the semantic colors: simulation blue #1F6FB2, measurement red #A2462E, model green #4B6B2F.
Do not add a backend, database or authentication.
```
**למה הבאנר:** כדי שאף אחד לא יתבלבל בין מספרי דמה לבין תוצאות. העיקרון הזה מחייב את כל הפרויקט.

## Google AI Studio — פרומפט 2 (אופציונלי): ניסוי UI על הקוד האמיתי

מייבאים את ה-repo מ-GitHub (`+` ← Import from GitHub) **על ענף נפרד** (למשל `ui-experiment`), ושולחים:
```
This repo is a React 19 + TypeScript + Vite frontend (frontend/) with a Python FastAPI backend
(backend/). Work ONLY inside frontend/src/styles.css and presentational JSX.
INVARIANTS — do not violate:
- Do not change API calls, routes, data types, query keys, or any file under backend/.
- Do not change data-testid attributes or Hebrew strings in src/i18n/he.ts.
- Keep dir="rtl"; numbers/units/charts stay LTR.
- Do not add a Node server, Gemini calls, or new dependencies.
Task: apply the attached DESIGN.md tokens (colors, fonts, radii, spacing) to the existing
components. One component group per iteration; list the files you changed.
```
את השינויים מחזירים דרך GitHub sync, ואני מריץ עליהם את כל הבדיקות לפני מיזוג.

## העלאה לאוויר
לא דרך AI Studio. ההנחיות המלאות נמצאות ב-`docs/deploy-cloud-run.md`: קונטיינר אחד ב-Cloud Run באזור תל אביב (me-west1), מסד Cloud SQL Postgres (כ-8$ לחודש), ו-Cloud Run בחיוב לפי שימוש (בדרך כלל בתוך המכסה החינמית בהיקף של כיתה).

## מקורות
- [Introducing "vibe design" with Stitch](https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/) — DESIGN.md, MCP, ייצוא ל-AI Studio
- [Stitch Prompt Guide](https://discuss.ai.google.dev/t/stitch-prompt-guide/83844) · [Stitch llms.txt](https://stitch.withgoogle.com/llms.txt)
- [Stitch: באג בעברית/RTL](https://discuss.ai.google.dev/t/bug-in-ui-on-rtl-languages-hebrew/108000)
- [AI Studio Build mode](https://ai.google.dev/gemini-api/docs/aistudio-build-mode) · [Deploying](https://ai.google.dev/gemini-api/docs/aistudio-deploying) · [Starter Tier](https://cloud.google.com/blog/topics/developers-practitioners/the-starter-tier-for-google-ai-studio-explained)
- [Cloud Run pricing](https://cloud.google.com/run/pricing) · [Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts?hl=en)
