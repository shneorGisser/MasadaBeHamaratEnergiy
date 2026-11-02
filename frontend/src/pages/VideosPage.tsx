/**
 * Explanation videos (videos/scenes.py, rendered with Manim). The captions are burned into the
 * picture; under each player the transcript is a list of cues: clicking one seeks the video,
 * and the cue being spoken is highlighted.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { VIDEOS, type VideoInfo } from '../videos'

interface Cue {
  start: number
  end: number
  text: string
}

function Player({ v }: { v: VideoInfo }) {
  const ref = useRef<HTMLVideoElement>(null)
  const [cues, setCues] = useState<Cue[]>([])
  const [now, setNow] = useState(0)
  useEffect(() => {
    let alive = true
    fetch(`/videos/${v.id}.json`)
      .then((r) => (r.ok ? r.json() : { cues: [] }))
      .then((d: { cues: Cue[] }) => alive && setCues(d.cues))
      .catch(() => alive && setCues([]))
    return () => {
      alive = false
    }
  }, [v.id])
  const active = cues.findIndex((c) => now >= c.start && now < c.end)
  return (
    <article className="card stack video-card" id={v.id} data-testid={`video-${v.id}`}>
      <h2>{v.title}</h2>
      <p className="muted">{v.about}</p>
      <video
        ref={ref}
        controls
        preload="metadata"
        playsInline
        onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
        aria-describedby={`${v.id}-transcript`}
      >
        <source src={`/videos/${v.id}.webm`} type="video/webm" />
        <source src={`/videos/${v.id}.mp4`} type="video/mp4" />
      </video>
      {cues.length > 0 && (
        <details>
          <summary>תמליל (לחיצה על משפט מעבירה אליו)</summary>
          <ol className="transcript" id={`${v.id}-transcript`}>
            {cues.map((c, i) => (
              <li key={i}>
                <button
                  className={`cue${i === active ? ' on' : ''}`}
                  onClick={() => {
                    const el = ref.current
                    if (!el) return
                    el.currentTime = c.start + 0.01
                    setNow(c.start + 0.01)
                    void el.play().catch(() => undefined)
                  }}
                >
                  <span className="ltr small muted">{fmtTime(c.start)}</span> {c.text}
                </button>
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  )
}

function fmtTime(t: number): string {
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function VideosPage() {
  return (
    <div className="stack">
      <h1>סרטוני הסבר</h1>
      <p className="muted">
        כל עקומה בסרטונים היא העקומה שהסימולציה במעבדה מחשבת, וכל נקודה מדודה היא קריאה אמיתית מדוח מעבדה. הסרטונים נוצרים מקוד
        (Manim), כך שכשמודל מתעדכן הסרטון מתעדכן איתו.
      </p>
      {VIDEOS.map((v) => (
        <Player key={v.id} v={v} />
      ))}
      <p className="muted small">
        יש שאלה על סרטון, או רעיון לסרטון נוסף? <Link to="/">חזרה לפרויקטים</Link> או כפתור "משוב" בפינה.
      </p>
    </div>
  )
}
