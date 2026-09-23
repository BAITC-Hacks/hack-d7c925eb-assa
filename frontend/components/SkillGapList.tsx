import { SkillGap } from "../lib/types";

function Dots({ value, expected, required }: { value: number; expected: number; required: number }) {
  return <div className="dots" aria-label={`Текущий ${value}, ожидаемый ${expected}, требуемый ${required}`}>
    {[1,2,3,4,5].map(level => <span key={level} className={level <= value ? "filled" : level <= expected ? "expected" : level <= required ? "required" : ""} />)}
  </div>;
}

export function SkillGapList({ gaps }: { gaps: SkillGap[] }) {
  const active = gaps.filter(gap => (gap.expected_gap??1) > 0 || (gap.expected_level??0) > (gap.current_level??0));
  return (
    <section className="card">
      <div className="sectionTitle"><div><div className="eyebrow">КАРТА НАВЫКОВ</div><h2>Что отделяет вас от цели</h2></div><span className="pill">{active.filter(g => (g.expected_gap??1) > 0).length} gaps</span></div>
      <div className="legend"><span><i className="confirmed" /> подтверждено</span><span><i className="planned" /> ожидается</span><span><i className="need" /> требуется</span></div>
      <div className="gapList">
        {active.length ? active.map(gap => (
          <article className="gapRow" key={gap.skill_id}>
            <div><strong>{gap.name}</strong>{gap.critical && <em>ключевой</em>}<small>{gap.category}</small></div>
            <Dots value={gap.current_level??0} expected={gap.expected_level??0} required={gap.required_level} />
            <b>{gap.current_level??"Нет оценки"} → {gap.required_level}</b>
          </article>
        )) : <p className="empty">Все требования целевого профиля уже закрыты.</p>}
      </div>
    </section>
  );
}
