/** The explanation videos (videos/scenes.py) and the experiments each one explains. */

export interface VideoInfo {
  id: string
  title: string
  about: string
  /** experiments this video explains (ids of the registry) */
  experiments: string[]
}

export const VIDEOS: VideoInfo[] = [
  {
    id: 'RotatingField',
    title: 'השדה המגנטי המסתובב',
    about: 'שלושה ליפופים קבועים ושלושה זרמים מוזזים יוצרים שדה אחד שמסתובב. משם מגיעות המהירות הסינכרונית וההחלקה.',
    experiments: ['induction_motor', 'wound_rotor', 'synchronous'],
  },
  {
    id: 'TorqueSpeed',
    title: 'אופיין מומנט–מהירות',
    about: 'מעגל התמורה של מנוע ההשראה, חלוקת ההספק במרווח האוויר, נוסחת קלוס, ונקודות העומס שנמדדו ב-2026.',
    experiments: ['induction_motor', 'wound_rotor'],
  },
  {
    id: 'TransformerTests',
    title: 'בדיקות ריקם וקצר בשנאי',
    about: 'למה כל בדיקה חושפת חצי ממעגל התמורה, ואיך מחשבים ממנה R_fe, X_m, R_k ו-X_k. כולל טבלת 2025.',
    experiments: ['transformer3ph'],
  },
  {
    id: 'SyncOccScc',
    title: 'אופייני ריקם וקצר של המכונה הסינכרונית',
    about: 'הרוויה באופיין הריקם, הקו הישר של אופיין הקצר, והריאקטנס הסינכרוני ויחס הקצר שמתקבלים משניהם.',
    experiments: ['synchronous'],
  },
  {
    id: 'VCurves',
    title: 'עקומות V',
    about: 'זרם העירור קובע את ההספק הריאקטיבי ולא את הפעיל. תת-עירור, על-עירור, ומפצה סינכרוני.',
    experiments: ['synchronous'],
  },
]
