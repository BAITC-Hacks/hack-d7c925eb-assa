import { Career } from "../lib/types";

export function CareerPath({ career }: { career: Career }) {
  const { employee, target, progress } = career;
  const total = progress.remaining_gap || 1;
  const reduction = Math.max(0, progress.remaining_gap - progress.expected_remaining_gap);
  const percent = Math.min(100, Math.round((reduction / total) * 100));
  return (
    <section className="card heroCard">
      <div className="eyebrow">КАРЬЕРНЫЙ МАРШРУТ</div>
      <div className="path">
        <div><span>Сейчас</span><strong>{employee.role}</strong><b>{employee.grade}</b></div>
        <div className="pathLine"><i style={{ width: `${Math.max(8, percent)}%` }} /></div>
        <div><span>Цель</span><strong>{target.role}</strong><b>{target.grade}</b></div>
      </div>
      <div className="progressCopy">
        <span>Подтверждённый дефицит: <strong>{progress.remaining_gap}</strong></span>
        <span>Ожидаемый после активностей: <strong className="green">{progress.expected_remaining_gap}</strong></span>
      </div>
    </section>
  );
}
