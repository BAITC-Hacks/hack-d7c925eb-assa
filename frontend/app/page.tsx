"use client";

import { useEffect, useState } from "react";
import { CareerPath } from "../components/CareerPath";
import { RecommendationCard } from "../components/RecommendationCard";
import { SkillGapList } from "../components/SkillGapList";
import { api } from "../lib/api";
import { Career, Employee } from "../lib/types";

export default function EmployeePage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [employeeId, setEmployeeId] = useState("E0001");
  const [career, setCareer] = useState<Career | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.employees().then(setEmployees).catch(() => setError("Не удалось подключиться к API")); }, []);
  useEffect(() => {
    setCareer(null); setError("");
    api.career(employeeId).then(setCareer).catch(() => setError("Не удалось загрузить карьерный маршрут"));
  }, [employeeId]);

  async function complete(eventId: string) {
    setBusy(true);
    try { setCareer((await api.complete(employeeId, eventId)).career); }
    catch { setError("Не удалось завершить активность"); }
    finally { setBusy(false); }
  }

  return <main>
    <div className="pageHeading">
      <div><div className="eyebrow">CAREER GPS</div><h1>Ваш следующий карьерный шаг</h1><p>Понятный маршрут от текущих навыков к целевой роли.</p></div>
      <label className="employeeSelect">Профиль<select value={employeeId} onChange={e => setEmployeeId(e.target.value)}>{employees.map(employee => <option key={employee.employee_id} value={employee.employee_id}>{employee.full_name} · {employee.role}</option>)}</select></label>
    </div>
    {error && <div className="error">{error}. Убедитесь, что backend запущен на порту 8000.</div>}
    {!career && !error && <div className="loading">Строим маршрут…</div>}
    {career && <>
      <CareerPath career={career} />
      <div className="dashboardGrid">
        <SkillGapList gaps={career.gaps} />
        <section className="recommendations">
          <div className="sectionTitle"><div><div className="eyebrow">СЛЕДУЮЩЕЕ ДЕЙСТВИЕ</div><h2>Рекомендации</h2></div></div>
          {career.recommendations.length ? career.recommendations.map((item, index) => <RecommendationCard key={item.event_id} item={item} primary={index === 0} busy={busy} onComplete={() => complete(item.event_id)} />) : <div className="card empty">Для этого профиля сейчас нет подходящих добровольных активностей.</div>}
        </section>
      </div>
    </>}
  </main>;
}
