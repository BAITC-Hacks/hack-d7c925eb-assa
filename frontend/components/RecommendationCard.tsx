import { useState } from "react";
import { Recommendation } from "../lib/types";
import { ScoreBreakdown } from "./ScoreBreakdown";

export function RecommendationCard({ item, primary, busy, onComplete }: { item: Recommendation; primary?: boolean; busy: boolean; onComplete: () => void }) {
  const [open, setOpen] = useState(false);
  return <article className={`recommendation ${primary ? "primary" : ""}`}>
    <div className="recommendTop">
      <div><span className="pill">{primary ? "Лучший следующий шаг" : "Альтернатива"}</span><h3>{item.title}</h3></div>
      <button className="score" onClick={() => setOpen(!open)} aria-expanded={open}><strong>{item.score}</strong><span>из 100<br/>почему?</span></button>
    </div>
    <p>{item.explanation}</p>
    <div className="meta"><span>{item.format.replace("_", " ")}</span><span>{item.duration_hours} ч</span>{item.next_session && <span>{item.next_session}</span>}</div>
    {open && <ScoreBreakdown components={item.components} />}
    {primary && <button className="action" disabled={busy} onClick={onComplete}>{busy ? "Обновляем маршрут…" : "Отметить завершённой"}</button>}
  </article>;
}
