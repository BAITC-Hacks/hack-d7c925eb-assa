const paths: Record<string, string> = {
  compass: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm4 5-2 6-6 2 2-6 6-2Z",
  map: "m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Zm6-3v15m6-12v15",
  route: "M5 5h10a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h10M5 2v6m13 10 3 3-3 2",
  skills: "M12 3v5m0 8v5M3 12h5m8 0h5M5 5l4 4m6 6 4 4M5 19l4-4m6-6 4-4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z",
  history: "M3 10a9 9 0 1 1 2 8M3 4v6h6m3-3v5l3 2",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  up: "M12 20V4m-6 6 6-6 6 6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6",
  check: "m5 12 4 4L19 6",
  flag: "M5 22V3m0 0h7l2 3h6v10h-7l-2-3H5",
  lock: "M6 10h12v11H6V10Zm3 0V6a3 3 0 0 1 6 0v4m-3 4v3",
  gem: "m3 8 4-5h10l4 5-9 13L3 8Zm0 0h18M7 3l5 18 5-18",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l4 2",
  chart: "M4 20h17M7 16v-5m5 5V5m5 11V8",
  people: "M9 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm-6 17v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m1 3a5 5 0 0 1 4 5v2",
  award: "M12 3a6 6 0 1 0 0 12 6 6 0 0 0 0-12ZM8 14l-2 7 6-3 6 3-2-7",
  close: "m6 6 12 12M6 18 18 6",
  reset: "M4 11a8 8 0 1 1 2 7M4 4v7h7",
  leaf: "M4 20c0-10 6-16 16-16 0 10-6 16-16 16Zm0 0L15 9",
};
export function QuestIcon({ name, size = 20 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.compass} /></svg>;
}
