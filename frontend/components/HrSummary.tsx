import { HrSummary as HrSummaryType } from "../lib/types";

export function HrSummary({ data }: { data: HrSummaryType }) {
  const max = Math.max(...data.top_gaps.map(item => item.employees), 1);
  return <div className="hrGrid">
    <section className="card metricCard"><span>Completion rate</span><strong>{data.participation.completion_rate}%</strong><small>{data.participation.completed} из {data.participation.total_records} участий</small></section>
    <section className="card wide"><div className="sectionTitle"><div><div className="eyebrow">ОРГАНИЗАЦИЯ</div><h2>Самые частые дефициты</h2></div></div>
      <div className="barChart">{data.top_gaps.map(item => <div key={item.name}><span>{item.name}</span><div><i style={{ width: `${item.employees / max * 100}%` }} /></div><b>{item.employees}</b></div>)}</div>
    </section>
    <section className="card wide"><div className="sectionTitle"><div><div className="eyebrow">ТРЕБУЕТ ВНИМАНИЯ</div><h2>Без доступных рекомендаций</h2></div><span className="pill">{data.employees_without_recommendations.length}</span></div>
      <div className="peopleList">{data.employees_without_recommendations.slice(0, 8).map(person => <div key={person.employee_id}><b>{person.full_name}</b><span>{person.target_role}</span><small>{person.employee_id}</small></div>)}{!data.employees_without_recommendations.length && <p className="empty">У всех сотрудников с дефицитами есть следующий шаг.</p>}</div>
    </section>
  </div>;
}
