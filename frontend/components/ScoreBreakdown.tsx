const labels: Record<string, string> = {
  goal_priority: "Приоритет для цели",
  gap_reduction: "Сокращение gap",
  history_fit: "Соответствие истории",
  realism: "Реалистичность",
  time_efficiency: "Эффективность по времени",
};
const maximums: Record<string, number> = { goal_priority: 30, gap_reduction: 25, history_fit: 20, realism: 15, time_efficiency: 10 };

export function ScoreBreakdown({ components }: { components: Record<string, number> }) {
  return <div className="breakdown">
    <p>Это прозрачный рейтинг, а не вероятность успеха.</p>
    {Object.entries(components).map(([key, value]) => <div className="scoreRow" key={key}>
      <span>{labels[key]}</span><div><i style={{ width: `${value / maximums[key] * 100}%` }} /></div><b>{value}/{maximums[key]}</b>
    </div>)}
  </div>;
}
