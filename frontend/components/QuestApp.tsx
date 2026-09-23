"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, scopedApi } from "../lib/api";
import { CardAction, AgentReply, AppConfig, Artifact, Career, Employee, HrSummary, Recommendation, Session, View, GameReward } from "../lib/types";
import { QuestIcon as Icon } from "./QuestIcon";
import { EmployeeView, TeamView } from "./QuestViews";
import { GameSummary, RewardCelebration } from "./Gamification";

const labels: Record<View,string> = { comparison:"Сравнение", explanation:"Объяснение", clarification:"Уточнение", level:"Мой уровень", skill_map:"Карта навыков", route:"Мой маршрут", next_step:"Следующий шаг", history:"Моя история", hr_gaps:"Пульс команды", hr_coverage:"Без следующего шага", hr_events:"Участие", skill_guide:"Мастерская навыка", rewards:"Мои достижения" };
const navigation: [View,string][] = [["rewards","award"],["route","route"],["skill_map","skills"],["next_step","compass"],["history","history"]];
const hrNavigation: [View,string][] = [["hr_gaps","chart"],["hr_coverage","people"],["hr_events","history"]];
const toolLabels: Record<string,string> = { get_my_context:"Получить профиль и требования", find_development_options:"Подобрать допустимые активности", simulate_route:"Проверить ожидаемый результат", present_artifact:"Показать визуальный результат", get_skill_guide:"Прочитать справочник навыков", get_team_gaps:"Рассчитать дефициты отдела", get_coverage_gaps:"Проверить покрытие рекомендациями" };
type ChatMessage = { role: "user" | "assistant"; text: string; reply?: AgentReply; stale?: boolean; retry?: string; action?: CardAction };

function errorText(error: unknown) { return error instanceof Error ? error.message : "Не удалось выполнить запрос"; }

export function QuestApp({ initialRole = "employee" }: { initialRole?: Session["role"] }) {
  const [config,setConfig] = useState<AppConfig|null>(null);
  const [profiles,setProfiles] = useState<Employee[]>([]);
  const [session,setSession] = useState<Session|null>(null);
  const [role,setRole] = useState<Session["role"]>(initialRole);
  const [code,setCode] = useState("");
  const [error,setError] = useState("");
  const [switching,setSwitching] = useState(false);
  useEffect(()=>{
    let live=true;
    (async()=>{
      try {
        const c=await api.config(); if(!live)return; setConfig(c);
        const saved=sessionStorage.getItem("cq-session");
        if(saved){ try{const restored=await scopedApi(saved).restore();if(live)setSession({...restored,token:saved});if(c.demo){const list=await api.demoProfiles();if(live)setProfiles(list);}return;}catch{sessionStorage.removeItem("cq-session");} }
        if(c.demo){ const list=await api.demoProfiles(); if(!live)return; setProfiles(list); const s=await api.login("E0001",initialRole); if(live){setSession(s);sessionStorage.setItem("cq-session",s.token);} else await scopedApi(s.token).logout().catch(()=>{}); }
      } catch(e){ if(live)setError(errorText(e)); }
    })();
    return ()=>{live=false;};
  },[initialRole]);

  async function changeSession(employeeId: string, nextRole: Session["role"], accessCode="") {
    if(switching)return;
    setSwitching(true);setError("");
    try { const next=await api.login(employeeId,nextRole,accessCode); if(session)await scopedApi(session.token).logout().catch(()=>{}); setCode("");setRole(nextRole);setSession(next);sessionStorage.setItem("cq-session",next.token); }
    catch(e){setError(errorText(e));}
    finally{setSwitching(false);}
  }
  async function logout(){if(session)await scopedApi(session.token).logout().catch(()=>{});sessionStorage.removeItem("cq-session");setSession(null);}
  if(!config || !session) return <div className="welcome-shell"><div className="welcome-card"><div className="brand"><span className="brand-mark"><Icon name="compass" size={25}/></span>Career Quest</div><span className="eyebrow">ТВОЯ СЛЕДУЮЩАЯ ГЛАВА</span><h1>Развитие начинается<br/>с понятного шага.</h1><p className="muted">Карта навыков, личный маршрут и карьерный агент.</p>{error && <div className="error-box" role="alert">{error}<button className="text-button" onClick={()=>location.reload()}>Попробовать снова</button></div>}{config && !config.demo ? <form onSubmit={e=>{e.preventDefault();changeSession("E0001",role,code);}}><label>Режим<select value={role} onChange={e=>setRole(e.target.value as Session["role"])}><option value="employee">Сотрудник</option><option value="hr">HR</option></select></label><label>Код доступа<input type="password" value={code} onChange={e=>setCode(e.target.value)} autoComplete="current-password" required maxLength={256}/></label><button className="button primary" disabled={switching}>{switching?"Входим…":"Открыть мой путь"}</button><p className="tiny muted">Код выдаёт администратор. Выбор режима сам по себе не даёт прав.</p></form> : config?.demo && !error ? <><p className="muted">Подготавливаем синтетический профиль…</p><button className="button" disabled={switching} onClick={()=>changeSession("E0001",role)}>Открыть локальное демо</button></> : !error && <p className="muted">Подключаемся к Career Quest…</p>}</div></div>;
  return <Dashboard key={session.token} session={session} config={config} profiles={profiles} switching={switching} sessionError={error} changeSession={changeSession} logout={logout}/>;
}

function Dashboard({session,config,profiles,switching,sessionError,changeSession,logout}: {session:Session;config:AppConfig;profiles:Employee[];switching:boolean;sessionError:string;changeSession:(id:string,role:Session["role"])=>Promise<void>;logout:()=>Promise<void>}) {
  const client=useMemo(()=>scopedApi(session.token),[session.token]);
  const [career,setCareer]=useState<Career|null>(null);
  const [team,setTeam]=useState<HrSummary|null>(null);
  const stateKey=`cq-view:${session.employee_id}:${session.role}`;
  const [view,setView]=useState<View>(()=>{const saved=sessionStorage.getItem(stateKey) as View;return saved && (session.role==="hr"?hrNavigation:navigation).some(([id])=>id===saved)?saved:session.role==="hr"?"hr_gaps":"route";});
  const [artifact,setArtifact]=useState<Artifact|null>(null);
  const [messages,setMessages]=useState<ChatMessage[]>([]);
  const [input,setInput]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [reward,setReward]=useState<GameReward|null>(null);
  const [confirmation,setConfirmation]=useState<Recommendation|null>(null);
  const [chatOpen,setChatOpen]=useState(true);
  const [chatClosing,setChatClosing]=useState(false);
  const [lastReply,setLastReply]=useState<AgentReply|null>(null);
  const [loading,setLoading]=useState(true);
  const messagesEnd=useRef<HTMLDivElement>(null);
  const conversation=useRef<string>();
  useEffect(()=>{const resize=()=>document.documentElement.style.setProperty('--viewport-height',`${window.visualViewport?.height||window.innerHeight}px`);resize();window.visualViewport?.addEventListener('resize',resize);return()=>window.visualViewport?.removeEventListener('resize',resize);},[]);
  const inputRef=useRef<HTMLTextAreaElement>(null);
  const openButton=useRef<HTMLButtonElement>(null);
  const menuButton=useRef<HTMLButtonElement>(null);
  const sidebarRef=useRef<HTMLElement>(null);
  const scrollRef=useRef<HTMLDivElement>(null);
  const followScroll=useRef(true);
  const [hasNew,setHasNew]=useState(false);
  const [menuOpen,setMenuOpen]=useState(false);
  const [goals,setGoals]=useState<{role:string;grade:string}[]>([]);
  const [goalChoice,setGoalChoice]=useState("");
  const [recording,setRecording]=useState(false);
  const recognition=useRef<any>(null);
  useEffect(()=>{client.goals().then(setGoals).catch(()=>{});return()=>recognition.current?.stop();},[client]);
  useEffect(()=>{sessionStorage.setItem(stateKey,view);},[view,stateKey]);
  function closeChat(){setChatClosing(true);window.setTimeout(()=>{if(!alive.current)return;setChatOpen(false);setChatClosing(false);requestAnimationFrame(()=>{if(window.innerWidth<=760)menuButton.current?.focus();else openButton.current?.focus();});},window.matchMedia("(prefers-reduced-motion: reduce)").matches?0:300);}
  function closeMenu(){setMenuOpen(false);requestAnimationFrame(()=>menuButton.current?.focus());}
  useEffect(()=>{if(chatOpen)inputRef.current?.focus({preventScroll:true});},[chatOpen]);
  useEffect(()=>{if(menuOpen)sidebarRef.current?.querySelector<HTMLElement>("a,button,select")?.focus();},[menuOpen]);
  useEffect(()=>{const escape=(e:KeyboardEvent)=>{if(e.key==="Escape"){if(confirmation&&!busy)setConfirmation(null);else if(menuOpen)closeMenu();else if(chatOpen)closeChat();}};window.addEventListener("keydown",escape);return()=>window.removeEventListener("keydown",escape);},[chatOpen,menuOpen,confirmation,busy]);
  function voice(){
    if(recording){recognition.current?.stop();return;}
    const Speech=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
    if(!Speech){setError("Этот браузер не поддерживает голосовой ввод. Используйте текст.");return;}
    if(!window.confirm("Браузер может отправить запись своему сервису распознавания. Начать голосовой ввод?"))return;
    const r=new Speech();recognition.current=r;r.lang="ru-RU";r.interimResults=false;r.continuous=false;
    r.onresult=(event:any)=>{if(alive.current)setInput(old=>(old+" "+event.results[0][0].transcript).trim().slice(0,2000));};
    r.onend=()=>{if(alive.current)setRecording(false);};r.onerror=()=>{if(alive.current){setRecording(false);setError("Не удалось распознать речь. Проверьте разрешение микрофона или введите текст.");}};
    try{r.start();setRecording(true);}catch{setError("Микрофон недоступен. Используйте текст.");}
  }
  async function saveGoal(){if(!goalChoice||lock.current)return;const chosen=goals[Number(goalChoice)-1];if(!chosen)return;lock.current=true;setBusy(true);try{const c=await client.goal(session.employee_id,chosen.role,chosen.grade);if(alive.current){setCareer(c);setMessages(old=>old.map(m=>({...m,stale:!!m.reply})));setNotice("Цель сохранена. Маршрут пересчитан.");}}catch(e){if(alive.current)setError(errorText(e));}finally{lock.current=false;if(alive.current)setBusy(false);}}

  const alive=useRef(true);
  const request=useRef<AbortController|null>(null);
  const lock=useRef(false);
  const hr=session.role==="hr";
  useEffect(()=>{
    alive.current=true;
    const control=new AbortController();
    Promise.all([client.career(session.employee_id,control.signal),hr?client.hr(control.signal):Promise.resolve(null)]).then(([c,h])=>{if(alive.current){setCareer(c);setTeam(h);setLoading(false);}}).catch(e=>{if(!control.signal.aborted){setError(errorText(e));setLoading(false);}});
    return()=>{alive.current=false;control.abort();request.current?.abort();};
  },[client,session.employee_id,hr]);
  useEffect(()=>{if(!messages.length)return;if(followScroll.current)messagesEnd.current?.scrollIntoView({block:"nearest",behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});else setHasNew(true);},[messages.length,busy]);

  async function ask(text:string,reset=false,action?:CardAction){
    const message=text.trim();if(!message||lock.current||switching)return;
    lock.current=true;setBusy(true);setError("");setInput("");setChatOpen(true);
    setMessages(old=>[...old.slice(-39).map(m=>({...m,stale:!!m.reply})),{role:"user",text:message}]);
    const control=new AbortController();request.current=control;
    const timeout=window.setTimeout(()=>control.abort(),15000);
    try {
      const response=await client.assistant(message,reset,control.signal,conversation.current,action); if(!alive.current)return;
      conversation.current=response.conversation_id;setLastReply(response);setMessages(old=>[...old,{role:"assistant",text:response.answer,reply:response}]);
      if(response.artifact){setArtifact(response.artifact);if(response.artifact.career)setCareer(response.artifact.career);if(response.artifact.hr)setTeam(response.artifact.hr);}
    } catch(e){if(alive.current){setMessages(old=>[...old,{role:"assistant",retry:message,action,text:control.signal.aborted?"Ответ занял слишком много времени. Карта сохранена; попробуйте ещё раз.":errorText(e)}]);}}
    finally{clearTimeout(timeout);lock.current=false;if(alive.current)setBusy(false);}
  }

  async function complete(){
    if(!confirmation||lock.current)return;
    lock.current=true;setBusy(true);setError("");setReward(null);
    try {
      const response=await client.complete(session.employee_id,confirmation.event_id,confirmation.participation_id);
      if(!alive.current)return;
      setCareer(response.career);setArtifact(null);setLastReply(null);setConfirmation(null);
      if(!response.already_completed&&response.reward?.xp>0)setReward(response.reward);
      const text=response.already_completed
        ? "Это участие уже учтено. Повторный прирост и XP не начислены."
        : `Квест выполнен! +${response.reward?.xp??0} XP с учётом открытых наград. Ожидаемый прогресс обновлён; подтверждённый уровень и грейд не меняются.`;
      setNotice(text);
      setMessages(old=>[...old.map(m=>({...m,stale:!!m.reply})),{role:"assistant",text,reply:{answer:text,artifact:{kind:"skill_map",career:response.career},sources:[],trace:[],mode:"local",notice:"",elapsed_ms:0,constraints:{max_minutes:null,event_format:null},conversation_id:conversation.current||"",message_id:crypto.randomUUID()}}]);
    }
    catch(e){if(alive.current)setError(errorText(e));}
    finally{lock.current=false;if(alive.current)setBusy(false);}
  }
  function navigate(next:View){setView(next);setNotice("");setChatOpen(false);if(menuOpen)closeMenu();}
  const employee=career?.employee;
  const initials=employee?.full_name.split(" ").slice(0,2).map(s=>s[0]).join("")||"CQ";
  const questions=hr?["Какие навыки проседают в команде?","У кого нет следующего шага?","Какое участие по активностям?"]:["Покажи карту навыков","Построй маршрут","Мои достижения","У меня 30 минут"];
  const activeOptions=artifact?.options;
  return <div className={`quest-app ${chatOpen?"chat-open":""} ${menuOpen?"menu-open":""} ${chatClosing?"chat-closing":""}`}>
    <div className="mobile-topbar"><button ref={menuButton} className="button" aria-expanded={menuOpen} aria-controls="main-sidebar" onClick={()=>setMenuOpen(true)}>☰ Меню</button><strong>{chatOpen?"AI-чат":labels[view]}</strong></div>
    {menuOpen&&<button className="menu-backdrop" aria-label="Закрыть меню" onClick={closeMenu}/> }
    <aside className="sidebar" id="main-sidebar" ref={sidebarRef} inert={!!confirmation} onTransitionEnd={e=>{if(e.propertyName==="transform"&&menuOpen)sidebarRef.current?.querySelector<HTMLElement>("button,a,select")?.focus();}} aria-label="Основная навигация" onKeyDown={e=>{if(e.key!=="Tab"||!menuOpen)return;const items=sidebarRef.current?.querySelectorAll<HTMLElement>('a,button:not(:disabled),select:not(:disabled)');if(!items?.length)return;const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}>
      <button className="mobile-menu-close button" onClick={closeMenu}>Закрыть меню</button>
      <a className="brand" href="/" aria-label="Career Quest — главная"><span className="brand-mark"><Icon name="compass" size={24}/></span><span>Career<span className="brand-light">Quest</span></span></a>
      <div className="profile-block"><div className="avatar">{initials}<span/></div><strong>{employee?.full_name||"Загрузка профиля…"}</strong><span className="muted">{employee?.role}</span><span className="grade-badge">{employee?.grade||"…"}<span> · {hr?"HR":"Сотрудник"}</span></span></div>
      {config.demo?<div className="demo-controls"><label>Режим<select aria-label="Роль в демо" value={session.role} disabled={switching||busy} onChange={e=>changeSession(session.employee_id,e.target.value as Session["role"])}><option value="employee">Сотрудник</option><option value="hr">HR · мой отдел</option></select></label><label>Профиль демо<select aria-label="Профиль демо" value={session.employee_id} disabled={switching||busy} onChange={e=>changeSession(e.target.value,session.role)}>{profiles.map(p=><option key={p.employee_id} value={p.employee_id}>{p.full_name} · {p.grade}</option>)}</select></label></div>:<div className="private-label"><Icon name="shield" size={14}/>{hr?`HR · ${session.department}`:"Личный кабинет"}</div>}
      <div className="nav-label">{hr?"КОМАНДА":"МОЁ РАЗВИТИЕ"}</div><nav className="side-navigation" aria-label="Разделы"><button ref={openButton} className={chatOpen?"selected":""} aria-current={chatOpen?"page":undefined} onClick={()=>{setChatOpen(true);setMenuOpen(false);}}><Icon name="spark"/><span>AI-чат</span>{chatOpen&&<i/>}</button>{(hr?hrNavigation:navigation).map(([id,icon])=><button key={id} className={!chatOpen&&view===id?"selected":""} aria-current={!chatOpen&&view===id?"page":undefined} onClick={()=>navigate(id)}><Icon name={icon}/><span>{labels[id]}</span>{!chatOpen&&view===id&&<i/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="privacy-note"><Icon name="shield" size={19}/><span>Личный рост.<br/>Без сравнения с коллегами.</span></div><span className="environment-dot">{config.demo?"Локальное демо":"Защищённый пилот"}</span><small>Синтетические данные<br/>Срез {config.snapshot_date}</small><button className="text-button" onClick={logout}>Выйти из сессии</button></div>
    </aside>
    <main className="workspace" hidden={chatOpen} inert={menuOpen||!!confirmation}>
      <header className="workspace-heading"><div><div className="breadcrumbs">{hr?session.department:"Моё пространство"}<span>/</span>{labels[view]}</div><span className="eyebrow">{hr?"РАЗВИТИЕ, КОТОРОЕ ИМЕЕТ СМЫСЛ":"ТВОЯ СЛЕДУЮЩАЯ ГЛАВА"}</span><h1>{hr?"Помогаем команде расти":view==="rewards"?"Каждый шаг — достижение":view==="skill_map"?"Всё начинается с навыков":view==="history"?"Каждый шаг имеет значение":view==="skill_guide"?"От понимания — к практике":"От навыков — к цели"}</h1><p>{hr?"Где нужна поддержка и каких шагов пока не хватает.":view==="rewards"?"Собирай награды, открывай уровни и замечай свой прогресс.":"Понятный путь. Посильные квесты. Твой собственный темп."}</p></div><button className="mobile-agent button" onClick={()=>setChatOpen(!chatOpen)}><Icon name="spark"/>AI-чат</button></header>
      {sessionError&&<div className="error-box" role="alert">{sessionError}</div>}{error&&<div className="error-box" role="alert">{error}<button className="text-button" onClick={()=>location.reload()}>Переподключиться</button></div>}
      {notice&&<div className="success-note" role="status"><Icon name="check"/><span>{notice}</span><button aria-label="Закрыть уведомление" onClick={()=>setNotice("")}><Icon name="close" size={16}/></button></div>}
      {activeOptions&&(activeOptions.max_minutes||activeOptions.event_format)&&<div className="constraint-bar"><Icon name="clock" size={16}/><span>Условия маршрута: {activeOptions.max_minutes?`до ${activeOptions.max_minutes} мин`:"любое время"}{activeOptions.event_format?` · ${activeOptions.event_format === "self_paced"?"самостоятельно":activeOptions.event_format}`:""}</span><button className="text-button" disabled={busy} onClick={()=>ask("Построй маршрут без ограничений",true)}>Сбросить</button></div>}
      {!hr&&career&&view!=="rewards"&&<form className="goal-picker" onSubmit={e=>{e.preventDefault();saveGoal();}}><label htmlFor="career-goal">Карьерная цель</label><select id="career-goal" value={goalChoice} onChange={e=>setGoalChoice(e.target.value)}><option value="">{career.target.source==="career_goal"?`${career.target.role} · ${career.target.grade}`:"Цель не выбрана"}</option>{goals.map((g,i)=><option value={i+1} key={g.role+g.grade}>{g.role} · {g.grade}</option>)}</select><button className="button" disabled={!goalChoice||busy}>Сохранить цель</button></form>}
      {loading?<div className="loading-state"><span className="loading-orbit"><Icon name="compass" size={32}/></span><h2>Собираем твой маршрут</h2><p>Навыки, цели и подходящие возможности…</p></div>:hr&&team?<TeamView data={team} view={view} ask={ask} busy={busy}/>:career?<EmployeeView career={career} view={view} artifact={artifact} busy={busy} ask={ask} complete={setConfirmation}/>:null}
      <footer className="workspace-footer"><Icon name="leaf" size={14}/><span>Развитие — добровольный путь. Грейд и навыки подтверждаются отдельно.</span></footer>
    </main>
    <section className="agent-panel" inert={menuOpen||!!confirmation||!chatOpen} aria-label="Карьерный агент" aria-hidden={!chatOpen}>
      <div className="agent-heading"><div className="agent-symbol"><Icon name="spark" size={22}/></div><div><strong>Quest Agent</strong><span><i className={config.ai_enabled?"live":""}/>{config.ai_enabled?"AI-агент с инструментами":"Локальный помощник"}</span></div>{!hr&&career?.gamification&&<button className="game-header-pill" onClick={()=>navigate("rewards")} aria-label={`Мои достижения: игровой уровень ${career.gamification.level}, ${career.gamification.total_xp} XP`}><Icon name="gem" size={16}/><b>Ур. {career.gamification.level}</b><span>{career.gamification.total_xp} XP</span></button>}<button className="close-chat" aria-label="Свернуть чат" onClick={closeChat}><Icon name="close"/></button></div>
      <div ref={scrollRef} onScroll={()=>{const el=scrollRef.current;if(el)followScroll.current=el.scrollHeight-el.scrollTop-el.clientHeight<100;}} className="agent-conversation" role="log" aria-label="Диалог с агентом" aria-live="polite">
        {!messages.length?<div className="agent-intro"><div className="intro-symbol"><Icon name="spark" size={30}/></div><h2>{hr?"Видеть картину целиком":"Давай найдём твой путь"}</h2><p>{hr?"Покажу дефициты команды и объясню, почему у кого-то пока нет следующего шага.":"Помогу понять свой уровень, выбрать полезный шаг и увидеть, как он приближает к цели."}</p><div className="agent-capabilities"><span><Icon name="skills" size={16}/>Показать карту навыков</span><span><Icon name="route" size={16}/>Построить маршрут</span><span><Icon name="compass" size={16}/>Объяснить следующий шаг</span></div><div className="mode-note">{config.ai_enabled?"Агент сам выбирает инструменты. Данные и права проверяет сервер.":"Внешний AI выключен. Сейчас работают локальные команды и объяснения по базе."}</div>{!hr&&career?.gamification&&<GameSummary game={career.gamification} onOpen={()=>navigate("rewards")}/>}</div>:messages.map((m,i)=><div key={i} className={`chat-message ${m.role}`}><span className="message-author">{m.role==="user"?"Вы":"Quest Agent"}</span><div className="message-text">{m.text}</div>{m.retry&&<button className="button" disabled={busy} onClick={()=>ask(m.retry!,false,m.action)}>Повторить</button>}
        {m.reply?.artifact&&<div className={`chat-artifact ${m.stale?"stale":""}`}>{m.stale&&<p className="stale-label">Предыдущий результат · запросите обновление перед действием</p>}{m.reply.artifact.hr?<TeamView data={m.reply.artifact.hr} view={m.reply.artifact.kind} ask={ask} busy={busy||!!m.stale}/>:m.reply.artifact.career?<EmployeeView career={m.reply.artifact.career} view={m.reply.artifact.kind} artifact={m.reply.artifact} busy={busy||!!m.stale} ask={ask} complete={setConfirmation}/>:null}
        {!m.stale&&m.reply.artifact.options&&m.reply.artifact.options.recommendations.length>1&&<button className="button" disabled={busy} onClick={()=>ask("Сравни первые два варианта",false,{kind:"compare",event_ids:m.reply!.artifact!.options!.recommendations.slice(0,2).map(r=>r.event_id)})}>Сравнить варианты</button>}
        </div>}{m.reply&&<><div className="message-sources">{m.reply.sources.map(s=><button key={s.id} onClick={()=>s.id.startsWith("EV_")?ask(`Почему ${s.label}?`,false,{kind:"explain",event_ids:[s.id]}):navigate(s.view)}>{s.label}<Icon name="arrow" size={12}/></button>)}</div><details className="tool-trace"><summary>{m.reply.mode==="agent"?"Действия агента":"Выполненные инструменты"} · {m.reply.trace.length}</summary><ol>{m.reply.trace.map((t,index)=><li key={index}><span className={t.status==="ok"?"trace-ok":"trace-fail"}><Icon name={t.status==="ok"?"check":"close"} size={13}/></span><div>{toolLabels[t.tool]||t.tool}<code>{t.tool}</code></div><small>{t.ms} мс</small></li>)}</ol><small>{m.reply.elapsed_ms} мс всего</small></details><div className={`response-mode ${m.reply.mode}`}>{m.reply.mode==="agent"?"AI + проверенные данные":m.reply.mode==="fallback"?"Резервный локальный ответ":"Локальный ответ · без LLM"}</div>{m.reply.mode==="fallback"&&<p className="tiny muted">{m.reply.notice}</p>}</>}</div>)}
        {busy&&<div className="agent-working" role="status"><span className="working-dots"><i/><i/><i/></span>Обрабатываю запрос…</div>}<div ref={messagesEnd}/>
      </div>
      <div className="agent-input-area">{hasNew&&<button className="button" onClick={()=>{followScroll.current=true;setHasNew(false);messagesEnd.current?.scrollIntoView({block:"nearest"});}}>К последнему сообщению ↓</button>}{error&&<div className="error-box" role="alert">{error}</div>}<div className="quick-commands">{questions.map(q=><button key={q} disabled={busy||loading} onClick={()=>ask(q)}>{q}</button>)}</div><form className="chat-composer" onSubmit={(e:FormEvent)=>{e.preventDefault();ask(input);}}><label className="sr-only" htmlFor="agent-input">Сообщение агенту</label><textarea ref={inputRef} tabIndex={chatOpen?0:-1} id="agent-input" placeholder={hr?"Спроси о развитии команды…":"Что поможет мне расти?"} value={input} maxLength={2000} rows={2} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();ask(input);}}}/><div><button type="button" className="voice-button" aria-pressed={recording} onClick={voice}>{recording?"■ Стоп":"🎙 Голос"}</button><span>Enter — отправить</span><button aria-label="Отправить сообщение" disabled={busy||loading||!input.trim()}><Icon name="up" size={19}/></button></div></form><span className="agent-privacy"><Icon name="shield" size={12}/>Доступ только в пределах вашей роли</span></div>
    </section>
    {reward&&!confirmation&&<RewardCelebration xp={reward.xp} levelTitle={reward.level_title} levelUp={reward.level_up} badges={reward.badges} onClose={()=>setReward(null)}/> }
    {confirmation&&<div className="modal-backdrop" onClick={()=>{if(!busy)setConfirmation(null);}}><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="complete-title" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key!=="Tab")return;const buttons=e.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");if(buttons.length===2){e.preventDefault();(document.activeElement===buttons[0]?buttons[1]:buttons[0]).focus();}}}><span className="achievement-medal"><Icon name="flag" size={28}/></span><h2 id="complete-title">Квест действительно выполнен?</h2><h3>{confirmation.title}</h3><p>Отметка сохранится в истории и обновит ожидаемый прогресс. Подтверждённая оценка навыков и грейд останутся прежними.</p>{confirmation.reward_xp>0&&<p className="quest-reward"><Icon name="gem" size={18}/><strong>+{confirmation.reward_xp} XP</strong><span>и бонусы за новые достижения</span></p>}{error&&<div className="error-box" role="alert">{error}</div>}<div className="dialog-actions"><button autoFocus className="button" disabled={busy} onClick={()=>setConfirmation(null)}>Ещё прохожу</button><button className="button primary" disabled={busy} onClick={complete}>{busy?"Сохраняем…":"Да, выполнен"}</button></div></section></div>}
  </div>;
}
