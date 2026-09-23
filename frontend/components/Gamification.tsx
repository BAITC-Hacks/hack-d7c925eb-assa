"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { Gamification } from "../lib/types";
import { QuestIcon as Icon } from "./QuestIcon";

const number = (value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
const percent = (value: number, target: number) => target > 0 ? Math.max(0, Math.min(100, value / target * 100)) : 0;
const dateLabel = (value: string) => new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${value.slice(0, 10)}T12:00:00Z`));

function Progress({ value, label, gold = false }: { value: number; label: string; gold?: boolean }) {
  const bounded = Math.round(Math.max(0, Math.min(100, value)));
  return <div className={`gq-progress${gold ? " gq-progress-gold" : ""}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={bounded}>
    <span style={{ width: `${bounded}%` }} />
  </div>;
}

export function GameSummary({ game, onOpen }: { game: Gamification; onOpen: () => void }) {
  const earned = game.badges.filter(badge => badge.unlocked).length;
  return <section className="gq-summary" aria-label="Твой игровой прогресс">
    <div className="gq-summary-top">
      <span className="gq-summary-icon"><Icon name="gem" size={25} /></span>
      <div className="gq-summary-title"><span className="gq-kicker">ТВОЙ ИГРОВОЙ УРОВЕНЬ</span><strong>{game.level_title}</strong></div>
      <span className="gq-level-pill">Ур. {game.level}</span>
    </div>
    <div className="gq-summary-xp"><strong>{number(game.total_xp)} XP</strong><span>{game.xp_to_next_level > 0 ? `ещё ${number(game.xp_to_next_level)} до уровня ${game.level + 1}` : "Высший ранг открыт"}</span></div>
    <Progress value={game.level_progress_pct} label="Прогресс игрового уровня" />
    <div className="gq-summary-bottom"><span><Icon name="award" size={15} /> {earned}/{game.badges.length} наград</span><span><Icon name="leaf" size={15} /> Серия: {game.current_streak} нед.</span></div>
    <button className="gq-summary-link" type="button" onClick={onOpen}>Мои достижения <Icon name="arrow" size={17} /></button>
  </section>;
}

function ActivityCalendar({ days }: { days: Gamification["activity_days"] }) {
  const calendarId = useId();
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, days.length - 1));
  const cellRefs = useRef<(HTMLButtonElement | null)[]>([]);
  if (!days.length) return <p className="gq-empty">Первая выполненная активность появится здесь.</p>;
  const currentIndex = Math.min(selectedIndex, days.length - 1);
  const selectedDay = days[currentIndex];
  const activeDays = days.filter(day => day.count > 0).length;
  const maxCount = Math.max(1, ...days.map(day => day.count));

  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const shifts: Record<string, number> = { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 };
    let next = index;
    if (event.key in shifts) next += shifts[event.key];
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = days.length - 1;
    else return;
    event.preventDefault();
    next = Math.max(0, Math.min(days.length - 1, next));
    setSelectedIndex(next);
    cellRefs.current[next]?.focus();
  }

  return <>
    <div className="gq-calendar-summary"><strong>{activeDays} <span>дней с обучением</span></strong><span>за последние 12 недель</span></div>
    <div className="gq-calendar" role="group" aria-label="Календарь обучения за 12 недель. Для выбора дня используйте стрелки." aria-describedby={`${calendarId}-detail`}>
      <div className="gq-calendar-cells">
        {days.map((day, index) => <button
          key={day.date}
          ref={element => { cellRefs.current[index] = element; }}
          type="button"
          className={`gq-day gq-day-${day.count === 0 ? 0 : day.count / maxCount > .66 ? 3 : day.count / maxCount > .33 ? 2 : 1}`}
          aria-label={`${dateLabel(day.date)}: выполнено ${day.count}, ${number(day.xp)} XP`}
          aria-pressed={currentIndex === index}
          tabIndex={currentIndex === index ? 0 : -1}
          title={`${dateLabel(day.date)} · ${day.count} выполнено · ${number(day.xp)} XP`}
          onFocus={() => setSelectedIndex(index)}
          onClick={() => setSelectedIndex(index)}
          onKeyDown={event => navigate(event, index)}
        />)}
      </div>
    </div>
    <div className="gq-calendar-axis"><span>{dateLabel(days[0].date)}</span><span>{dateLabel(days[days.length - 1].date)}</span></div>
    <div className="gq-day-detail" id={`${calendarId}-detail`} aria-live="polite" aria-atomic="true">
      <Icon name={selectedDay.count ? "check" : "leaf"} size={17} />
      <div><strong>{dateLabel(selectedDay.date)}</strong><span>{selectedDay.count ? `Выполнено: ${selectedDay.count} · ${number(selectedDay.xp)} XP` : "Без завершённых активностей. Продолжай в своём темпе."}</span></div>
    </div>
    <div className="gq-calendar-legend"><span>Меньше</span><i className="gq-day-0" /><i className="gq-day-1" /><i className="gq-day-2" /><i className="gq-day-3" /><span>Больше</span><span className="gq-calendar-hint">Выбери день, чтобы увидеть детали</span></div>
  </>;
}

export function GameDashboard({ game, onFindQuest, busy }: { game: Gamification; onFindQuest: () => void; busy: boolean }) {
  const [badgeFilter, setBadgeFilter] = useState<"all" | "unlocked" | "locked">("all");
  const collectionId = useId();
  const earned = game.badges.filter(badge => badge.unlocked).length;
  const completedMissions = game.missions.filter(mission => mission.completed).length;
  const visibleBadges = game.badges.filter(badge => badgeFilter === "all" || (badgeFilter === "unlocked" ? badge.unlocked : !badge.unlocked));
  const filters = [
    { id: "all" as const, title: "Все", count: game.badges.length },
    { id: "unlocked" as const, title: "Открыты", count: earned },
    { id: "locked" as const, title: "Впереди", count: game.badges.length - earned },
  ];
  return <div className="gq-dashboard">
    <section className="gq-hero" aria-label="Игровой уровень и опыт">
      <div className="gq-hero-copy">
        <span className="gq-kicker"><Icon name="spark" size={15} /> КАЖДЫЙ ШАГ ИМЕЕТ ЗНАЧЕНИЕ</span>
        <h2>{game.level_title}</h2>
        <p>Учись, проходи квесты и собирай доказательства своего движения вперёд.</p>
        <div className="gq-hero-xp"><strong>{number(game.total_xp)} <span>XP</span></strong><span className="gq-hero-level">Игровой уровень {game.level}</span></div>
        <Progress value={game.level_progress_pct} label={`Уровень ${game.level}. ${number(game.xp_to_next_level)} XP до следующего уровня`} gold />
        <div className="gq-hero-progress-label"><span>{game.xp_to_next_level > 0 ? `${number(game.xp_to_next_level)} XP до следующего уровня` : "Все вершины открыты. Продолжай расти!"}</span><b>{Math.round(game.level_progress_pct)}%</b></div>
        <button className="gq-find-button" type="button" disabled={busy} onClick={onFindQuest}>Выбрать следующий квест <Icon name="arrow" size={18} /></button>
      </div>
      <div className="gq-rank-display" aria-hidden="true">
        <span className="gq-orbit gq-orbit-one" /><span className="gq-orbit gq-orbit-two" />
        <span className="gq-rank-spark gq-rank-spark-one"><Icon name="spark" size={23} /></span>
        <span className="gq-rank-spark gq-rank-spark-two"><Icon name="spark" size={14} /></span>
        <div className="gq-rank-crest"><Icon name="gem" size={53} /><strong>{game.level.toString().padStart(2, "0")}</strong><span>УРОВЕНЬ</span></div>
        <span className="gq-rank-ribbon">CAREER QUEST</span>
      </div>
    </section>

    <p className="gq-fair-play"><Icon name="shield" size={16} /> XP и игровой уровень отражают обучение. Профессиональный грейд подтверждается отдельно.</p>

    <section className="gq-stats" aria-label="Твои результаты">
      {[
        { icon: "flag", value: number(game.completed_quests), label: "квестов выполнено", note: "Каждый доведён до конца" },
        { icon: "clock", value: number(game.learning_hours), label: "часов обучения", note: "Вложено в своё развитие" },
        { icon: "skills", value: number(game.skill_count), label: "навыков в обучении", note: "Развивались через квесты" },
        { icon: "award", value: `${earned}/${game.badges.length}`, label: "наград в коллекции", note: "Твои личные вехи" },
      ].map(stat => <article className="gq-stat" key={stat.icon}><span className="gq-stat-icon"><Icon name={stat.icon} size={20} /></span><strong>{stat.value}</strong><span className="gq-stat-label">{stat.label}</span><small>{stat.note}</small></article>)}
    </section>

    <section className="gq-missions-section" aria-label="Личные миссии">
      <div className="gq-section-heading"><div><span className="gq-kicker">НЕБОЛЬШИЕ ЦЕЛИ → НОВЫЕ ВОЗМОЖНОСТИ</span><h2>Личные миссии</h2></div><span className="gq-count-pill">{completedMissions}/{game.missions.length} выполнено</span></div>
      <p className="gq-section-copy">Награды за миссии и достижения начисляются автоматически при выполнении условий.</p>
      <div className="gq-missions">
        {game.missions.map((mission, index) => <article className={`gq-mission${mission.completed ? " gq-mission-done" : ""}`} key={mission.id}>
          <div className="gq-mission-top"><span className="gq-mission-icon"><Icon name={mission.completed ? "check" : ["flag", "clock", "skills", "leaf"][index % 4]} size={21} /></span><span className={`gq-xp-pill${mission.completed ? " gq-xp-earned" : ""}`}>{mission.completed ? "Получено" : "Награда"} · +{number(mission.reward_xp)} XP</span></div>
          <h3>{mission.title}</h3><p>{mission.description}</p>
          <div className="gq-mission-progress-label"><span>{mission.completed ? "Миссия выполнена" : "Твой прогресс"}</span><strong>{number(Math.min(mission.progress, mission.target))} / {number(mission.target)}</strong></div>
          <Progress value={percent(mission.progress, mission.target)} label={`${mission.title}: ${number(mission.progress)} из ${number(mission.target)}`} />
        </article>)}
      </div>
    </section>

    <section aria-labelledby={`${collectionId}-heading`}>
      <div className="gq-section-heading"><div><span className="gq-kicker">ТВОЯ ИСТОРИЯ В СИМВОЛАХ</span><h2 id={`${collectionId}-heading`}>Коллекция достижений</h2></div><span className="gq-count-pill"><Icon name="award" size={14} /> {earned} открыто</span></div>
      <div className="gq-collection-toolbar"><p className="gq-section-copy">У каждой награды — понятное условие и следующий шаг.</p><div className="gq-filters" role="group" aria-label="Фильтр достижений">{filters.map(filter => <button type="button" key={filter.id} aria-pressed={badgeFilter === filter.id} aria-controls={`${collectionId}-items`} onClick={() => setBadgeFilter(filter.id)}>{filter.title}<span>{filter.count}</span></button>)}</div></div>
      <div className="gq-badges" id={`${collectionId}-items`}>
        {visibleBadges.map(badge => <article className={`gq-badge-card${badge.unlocked ? " gq-badge-unlocked" : ""}`} key={badge.id}>
          <div className="gq-badge-top"><span className="gq-badge-medallion"><Icon name={badge.icon} size={30} /></span><span className={`gq-badge-state${badge.unlocked ? " gq-badge-state-done" : ""}`}><Icon name={badge.unlocked ? "check" : "lock"} size={13} />{badge.unlocked ? "Открыто" : "Впереди"}</span></div>
          <h3>{badge.title}</h3><p>{badge.description}</p>
          <div className="gq-badge-bottom"><span>+{number(badge.reward_xp)} XP</span><strong>{number(Math.min(badge.progress, badge.target))}/{number(badge.target)}</strong></div>
          <Progress value={percent(badge.progress, badge.target)} label={`${badge.title}: ${badge.unlocked ? "награда открыта" : `${number(badge.progress)} из ${number(badge.target)}`}`} gold={badge.unlocked} />
        </article>)}
      </div>
      {!visibleBadges.length && <div className="gq-empty"><Icon name={badgeFilter === "unlocked" ? "gem" : "award"} size={28} /><strong>{badgeFilter === "unlocked" ? "Первая награда уже на горизонте" : "Коллекция собрана!"}</strong><p>{badgeFilter === "unlocked" ? "Пройди подходящий квест — он приблизит тебя к первым достижениям." : "Все доступные достижения открыты. Продолжай обучение и пополняй опыт."}</p>{badgeFilter === "unlocked" && <button className="gq-secondary-button" type="button" disabled={busy} onClick={onFindQuest}>Найти квест <Icon name="arrow" size={16} /></button>}</div>}
    </section>

    <section className="gq-level-section" aria-label="Путь игровых уровней">
      <div className="gq-section-heading"><div><span className="gq-kicker">РАСТИ В СВОЁМ ТЕМПЕ</span><h2>Путь к новым вершинам</h2></div><Icon name="route" size={24} /></div>
      <ol className="gq-level-path">{game.milestones.map(milestone => <li className={`${milestone.reached ? "gq-level-reached" : "gq-level-ahead"}${milestone.level === game.level ? " gq-level-current" : ""}`} key={milestone.level} aria-current={milestone.level === game.level ? "step" : undefined}>
        <span className="gq-level-node">{milestone.reached && milestone.level !== game.level ? <Icon name="check" size={18} /> : milestone.level}</span>
        <div><span className="gq-level-caption">{milestone.level === game.level ? "ТЫ ЗДЕСЬ" : `УРОВЕНЬ ${milestone.level}`}</span><strong>{milestone.title}</strong><span className="gq-level-threshold">{number(milestone.xp)} XP</span></div>
      </li>)}</ol>
    </section>

    <div className="gq-rhythm-grid">
      <section className="gq-panel gq-rhythm-panel" aria-label="Ритм обучения">
        <div className="gq-panel-heading"><span className="gq-panel-icon"><Icon name="leaf" size={22} /></span><h2>Твой ритм</h2></div>
        <div className="gq-streak-number"><strong>{game.current_streak}</strong><span>нед. подряд<br />с обучением</span></div>
        <div className="gq-streak-best"><Icon name="award" size={17} /><span>Лучшая серия</span><strong>{game.best_streak} нед.</strong></div>
        <p>Один завершённый квест в неделю поддерживает серию. Паузы не отнимают XP и награды.</p>
        <div className="gq-rhythm-note"><Icon name="spark" size={17} /><span>Устойчивый ритм важнее спешки.</span></div>
      </section>
      <section className="gq-panel gq-calendar-panel" aria-label="Календарь активности">
        <div className="gq-panel-heading"><span className="gq-panel-icon"><Icon name="history" size={22} /></span><h2>Календарь движения</h2></div>
        <ActivityCalendar days={game.activity_days} />
      </section>
    </div>

    <section className="gq-panel gq-rewards-panel" aria-label="Последние награды">
      <div className="gq-panel-heading"><span className="gq-panel-icon"><Icon name="gem" size={22} /></span><h2>История наград</h2><span className="gq-reward-total">Всего {number(game.total_xp)} XP</span></div>
      {game.recent_rewards.length ? <ol className="gq-rewards-list">{game.recent_rewards.map(reward => <li key={reward.id}><span className={`gq-reward-icon${reward.id.startsWith("badge:") ? " gq-reward-gold" : ""}`}><Icon name={reward.id.startsWith("badge:") ? "award" : reward.id.startsWith("mission:") ? "flag" : "check"} size={19} /></span><div><strong>{reward.title}</strong><span>{dateLabel(reward.date)} · {reward.source}</span></div><b>+{number(reward.xp)} XP</b></li>)}</ol> : <div className="gq-empty"><Icon name="flag" size={28} /><strong>Здесь начинается твоя история</strong><p>Заверши первый квест, чтобы получить опыт и увидеть свою награду.</p></div>}
    </section>
    <p className="gq-data-note"><Icon name="clock" size={15} /> Демо на синтетических данных. Прогресс и календарь рассчитаны на {dateLabel(game.as_of)}.</p>
  </div>;
}

export function RewardCelebration({ xp, levelTitle, levelUp, badges, onClose }: { xp: number; levelTitle: string; levelUp: boolean; badges: string[]; onClose: () => void }) {
  return <section className="gq-celebration" aria-label="Награда за выполненный квест">
    <span className="gq-celebration-icon"><Icon name={levelUp ? "gem" : "award"} size={30} /></span>
    <div className="gq-celebration-copy" role="status" aria-live="polite" aria-atomic="true"><span className="gq-kicker">{levelUp ? "НОВАЯ ВЕРШИНА" : "КВЕСТ ЗАВЕРШЁН"}</span><strong>+{number(xp)} XP <Icon name="spark" size={19} /></strong><p>{levelUp ? `Игровой уровень повышен · ${levelTitle}` : "Ещё один шаг к твоей цели!"}</p>{badges.length > 0 && <p className="gq-celebration-badges"><Icon name="award" size={14} /> Открыто: {badges.join(" · ")}</p>}</div>
    <button className="gq-celebration-close" type="button" aria-label="Скрыть награду" onClick={onClose}><Icon name="close" size={18} /></button>
  </section>;
}
