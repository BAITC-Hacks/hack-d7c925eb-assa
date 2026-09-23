"use client";

import { useEffect, useState } from "react";
import { HrSummary } from "../../components/HrSummary";
import { api } from "../../lib/api";
import { HrSummary as HrSummaryType } from "../../lib/types";

export default function HrPage() {
  const [data, setData] = useState<HrSummaryType | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.hrSummary().then(setData).catch(() => setError("Не удалось загрузить HR-сводку")); }, []);
  return <main><div className="pageHeading"><div><div className="eyebrow">HR VIEW</div><h1>Пульс развития команды</h1><p>Дефициты навыков, участие и точки, где нужна помощь.</p></div></div>
    {error && <div className="error">{error}</div>}
    {!data && !error && <div className="loading">Собираем аналитику…</div>}
    {data && <HrSummary data={data} />}
  </main>;
}
