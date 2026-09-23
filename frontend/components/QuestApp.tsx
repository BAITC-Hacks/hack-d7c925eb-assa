"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, scopedApi } from "../lib/api";
import { AgentReply, AppConfig, Artifact, Career, Employee, HrSummary, Recommendation, Session, View } from "../lib/types";
import { QuestIcon as Icon } from "./QuestIcon";
import { EmployeeView, TeamView } from "./QuestViews";

const labels: Record<View,string> = { level:"Мой уровень", skill_map:"Карта навыков", route:"Мой маршрут", next_step:"Следующий шаг", history:"Моя история", hr_gaps:"Пульс команды", hr_coverage:"Без следующего шага", hr_events:"Участие", skill_guide:"Мастерская навыка" };
const navigation: [View,string][] = [["route","route"],["skill_map","skills"],["next_step","compass"],["history","history"]];
const hrNavigation: [View,string][] = [["hr_gaps","chart"],["hr_coverage","people"],["hr_events","history"]];
const toolLabels: Record<string,string> = { get_my_context:"Получить профиль и требования", find_development_options:"Подобрать допустимые активности", simulate_route:"Проверить ожидаемый результат", present_artifact:"Показать визуальный результат", get_skill_guide:"Прочитать справочник навыков", get_team_gaps:"Рассчитать дефициты отдела", get_coverage_gaps:"Проверить покрытие рекомендациями" };
type ChatMessage = { role: "user" | "assistant"; text: string; reply?: AgentReply };

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
        if(c.demo){ const list=await api.demoProfiles(); if(!live)return; setProfiles(list); const s=await api.login("E0001",initialRole); if(live)setSession(s); else await scopedApi(s.token).logout().catch(()=>{}); }
      } catch(e){ if(live)setError(errorText(e)); }
    })();
    return ()=>{live=false;};
  },[initialRole]);

  async function changeSession(employeeId: string, nextRole: Session["role"], accessCode="") {
    if(switching)return;
    setSwitching(true);setError("");
    try { const next=await api.login(employeeId,nextRole,accessCode); if(session)await scopedApi(session.token).logout().catch(()=>{}); setCode("");setRole(nextRole);setSession(next); }
    catch(e){setError(errorText(e));}
    finally{setSwitching(false);}
  }
  async function logout(){if(session)await scopedApi(session.token).logout().catch(()=>{});setSession(null);}
  if(!config || !session) return <div className="welcome-shell"><div className="welcome-card"><div className="brand"><span className="brand-mark"><Icon name="compass" size={25}/></span>Career Quest</div><span className="eyebrow">ТВОЯ СЛЕДУЮЩАЯ ГЛАВА</span><h1>Развитие начинается<br/>с понятного шага.</h1><p className="muted">Карта навыков, личный маршрут и карьерный агент.</p>{error && <div className="error-box" role="alert">{error}<button className="text-button" onClick={()=>location.reload()}>Попробовать снова</button></div>}{config && !config.demo ? <form onSubmit={e=>{e.preventDefault();changeSession("E0001",role,code);}}><label>Режим<select value={role} onChange={e=>setRole(e.target.value as Session["role"])}><option value="employee">Сотрудник</option><option value="hr">HR</option></select></label><label>Код доступа<input type="password" value={code} onChange={e=>setCode(e.target.value)} autoComplete="current-password" required maxLength={256}/></label><button className="button primary" disabled={switching}>{switching?"Входим…":"Открыть мой путь"}</button><p className="tiny muted">Код выдаёт администратор. Выбор режима сам по себе не даёт прав.</p></form> : config?.demo && !error ? <><p className="muted">Подготавливаем синтетический профиль…</p><button className="button" disabled={switching} onClick={()=>changeSession("E0001",role)}>Открыть локальное демо</button></> : !error && <p className="muted">Подключаемся к Career Quest…</p>}</div></div>;
  return <Dashboard key={session.token} session={session} config={config} profiles={profiles} switching={switching} sessionError={error} changeSession={changeSession} logout={logout}/>;
}

function Dashboard({session,config,profiles,switching,sessionError,changeSession,logout}: {session:Session;config:AppConfig;profiles:Employee[];switching:boolean;sessionError:string;changeSession:(id:string,role:Session["role"])=>Promise<void>;logout:()=>Promise<void>}) {
  const client=useMemo(()=>scopedApi(session.token),[session.token]);
  const [career,setCareer]=useState<Career|null>(null);
  const [team,setTeam]=useState<HrSummary|null>(null);
  const [view,setView]=useState<View>(session.role==="hr"?"hr_gaps":"route");
  const [artifact,setArtifact]=useState<Artifact|null>(null);
  const [messages,setMessages]=useState<ChatMessage[]>([]);
  const [input,setInput]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [confirmation,setConfirmation]=useState<Recommendation|null>(null);
  const [chatOpen,setChatOpen]=useState(false);
  const [lastReply,setLastReply]=useState<AgentReply|null>(null);
  const [loading,setLoading]=useState(true);
  const messagesEnd=useRef<HTMLDivElement>(null);
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
  useEffect(()=>{if(messages.length)messagesEnd.current?.scrollIntoView({block:"nearest",behavior:"smooth"});},[messages.length,busy]);

  async function ask(text:string,reset=false){
    const message=text.trim();if(!message||lock.current||switching)return;
    lock.current=true;setBusy(true);setError("");setInput("");setChatOpen(true);
    setMessages(old=>[...old.slice(-19),{role:"user",text:message}]);
    const control=new AbortController();request.current=control;
    const timeout=window.setTimeout(()=>control.abort(),15000);
    try {
      const response=await client.assistant(message,reset,control.signal); if(!alive.current)return;
      setLastReply(response);setMessages(old=>[...old,{role:"assistant",text:response.answer,reply:response}]);
      if(response.artifact){setArtifact(response.artifact);setView(response.artifact.kind);if(response.artifact.career)setCareer(response.artifact.career);if(response.artifact.hr)setTeam(response.artifact.hr);}
    } catch(e){if(alive.current){setMessages(old=>[...old,{role:"assistant",text:control.signal.aborted?"Ответ занял слишком много времени. Карта сохранена; попробуйте ещё раз.":errorText(e)}]);}}
    finally{clearTimeout(timeout);lock.current=false;if(alive.current)setBusy(false);}
  }

  async function complete(){
    if(!confirmation||lock.current)return;
    lock.current=true;setBusy(true);setError("");
    try{const response=await client.complete(session.employee_id,confirmation.event_id);if(!alive.current)return;setCareer(response.career);setArtifact(null);setLastReply(null);setMessages([]);setView("route");setConfirmation(null);setNotice(response.already_completed?"Это выполнение уже учтено. Повторный прирост не начислен.":"Квест завершён. Ожидаемый прогресс обновлён; подтверждённый уровень и грейд сохранены.");}
    catch(e){if(alive.current)setError(errorText(e));}
    finally{lock.current=false;if(alive.current)setBusy(false);}
  }
  function navigate(next:View){setView(next);setNotice("");}
  const employee=career?.employee;
  const initials=employee?.full_name.split(" ").slice(0,2).map(s=>s[0]).join("")||"CQ";
  const questions=hr?["Какие навыки проседают в команде?","У кого нет следующего шага?"]:["Покажи карту навыков","Построй маршрут","У меня 30 минут"];
  const activeOptions=artifact?.options;
  return <div className={`quest-app ${chatOpen?"chat-open":""}`}>
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Career Quest — главная"><span className="brand-mark"><Icon name="compass" size={24}/></span><span>Career<span className="brand-light">Quest</span></span></a>
      <div className="profile-block"><div className="avatar">{initials}<span/></div><strong>{employee?.full_name||"Загрузка профиля…"}</strong><span className="muted">{employee?.role}</span><span className="grade-badge">{employee?.grade||"…"}<span> · {hr?"HR":"Сотрудник"}</span></span></div>
      {config.demo?<div className="demo-controls"><label>Режим<select aria-label="Роль в демо" value={session.role} disabled={switching||busy} onChange={e=>changeSession(session.employee_id,e.target.value as Session["role"])}><option value="employee">Сотрудник</option><option value="hr">HR · мой отдел</option></select></label><label>Профиль демо<select aria-label="Профиль демо" value={session.employee_id} disabled={switching||busy} onChange={e=>changeSession(e.target.value,session.role)}>{profiles.map(p=><option key={p.employee_id} value={p.employee_id}>{p.full_name} · {p.grade}</option>)}</select></label></div>:<div className="private-label"><Icon name="shield" size={14}/>{hr?`HR · ${session.department}`:"Личный кабинет"}</div>}
      <div className="nav-label">{hr?"КОМАНДА":"МОЁ РАЗВИТИЕ"}</div><nav className="side-navigation" aria-label="Разделы">{(hr?hrNavigation:navigation).map(([id,icon])=><button key={id} className={view===id?"selected":""} aria-current={view===id?"page":undefined} onClick={()=>navigate(id)}><Icon name={icon}/><span>{labels[id]}</span>{view===id&&<i/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="privacy-note"><Icon name="shield" size={19}/><span>Личный рост.<br/>Без сравнения с коллегами.</span></div><span className="environment-dot">{config.demo?"Локальное демо":"Защищённый пилот"}</span><small>Синтетические данные<br/>Срез {config.snapshot_date}</small><button className="text-button" onClick={logout}>Выйти из сессии</button></div>
    </aside>
    <main className="workspace">
      <header className="workspace-heading"><div><div className="breadcrumbs">{hr?session.department:"Моё пространство"}<span>/</span>{labels[view]}</div><span className="eyebrow">{hr?"РАЗВИТИЕ, КОТОРОЕ ИМЕЕТ СМЫСЛ":"ТВОЯ СЛЕДУЮЩАЯ ГЛАВА"}</span><h1>{hr?"Помогаем команде расти":view==="skill_map"?"Всё начинается с навыков":view==="history"?"Каждый шаг имеет значение":view==="skill_guide"?"От понимания — к практике":"От навыков — к цели"}</h1><p>{hr?"Где нужна поддержка и каких шагов пока не хватает.":"Понятный путь. Посильные квесты. Твой собственный темп."}</p></div><button className="mobile-agent button" onClick={()=>setChatOpen(!chatOpen)}><Icon name="spark"/>Агент</button></header>
      {sessionError&&<div className="error-box" role="alert">{sessionError}</div>}{error&&<div className="error-box" role="alert">{error}<button className="text-button" onClick={()=>location.reload()}>Переподключиться</button></div>}
      {notice&&<div className="success-note" role="status"><Icon name="check"/><span>{notice}</span><button aria-label="Закрыть уведомление" onClick={()=>setNotice("")}><Icon name="close" size={16}/></button></div>}
      {activeOptions&&(activeOptions.max_minutes||activeOptions.event_format)&&<div className="constraint-bar"><Icon name="clock" size={16}/><span>Условия маршрута: {activeOptions.max_minutes?`до ${activeOptions.max_minutes} мин`:"любое время"}{activeOptions.event_format?` · ${activeOptions.event_format === "self_paced"?"самостоятельно":activeOptions.event_format}`:""}</span><button className="text-button" disabled={busy} onClick={()=>ask("Построй маршрут без ограничений",true)}>Сбросить</button></div>}
      {loading?<div className="loading-state"><span className="loading-orbit"><Icon name="compass" size={32}/></span><h2>Собираем твой маршрут</h2><p>Навыки, цели и подходящие возможности…</p></div>:hr&&team?<TeamView data={team} view={view} ask={ask} busy={busy}/>:career?<EmployeeView career={career} view={view} artifact={artifact} busy={busy} ask={ask} complete={setConfirmation}/>:null}
      <footer className="workspace-footer"><Icon name="leaf" size={14}/><span>Развитие — добровольный путь. Грейд и навыки подтверждаются отдельно.</span></footer>
    </main>
    <aside className="agent-panel" aria-label="Карьерный агент">
      <div className="agent-heading"><div className="agent-symbol"><Icon name="spark" size={22}/></div><div><strong>Quest Agent</strong><span><i className={config.ai_enabled?"live":""}/>{config.ai_enabled?"AI-агент с инструментами":"Локальный помощник"}</span></div><button className="close-chat" aria-label="Свернуть чат" onClick={()=>setChatOpen(false)}><Icon name="close"/></button></div>
      <div className="agent-conversation" role="log" aria-label="Диалог с агентом" aria-live="polite">
        {!messages.length?<div className="agent-intro"><div className="intro-symbol"><Icon name="spark" size={30}/></div><h2>{hr?"Видеть картину целиком":"Давай найдём твой путь"}</h2><p>{hr?"Покажу дефициты команды и объясню, почему у кого-то пока нет следующего шага.":"Помогу понять свой уровень, выбрать полезный шаг и увидеть, как он приближает к цели."}</p><div className="agent-capabilities"><span><Icon name="skills" size={16}/>Показать карту навыков</span><span><Icon name="route" size={16}/>Построить маршрут</span><span><Icon name="compass" size={16}/>Объяснить следующий шаг</span></div><div className="mode-note">{config.ai_enabled?"Агент сам выбирает инструменты. Данные и права проверяет сервер.":"Внешний AI выключен. Сейчас работают локальные команды и объяснения по базе."}</div></div>:messages.map((m,i)=><div key={i} className={`chat-message ${m.role}`}><span className="message-author">{m.role==="user"?"Вы":"Quest Agent"}</span><div className="message-text">{m.text}</div>{m.reply&&<><div className="message-sources">{m.reply.sources.map(s=><button key={s.id} onClick={()=>navigate(s.view)}>{s.label}<Icon name="arrow" size={12}/></button>)}</div><details className="tool-trace"><summary>{m.reply.mode==="agent"?"Действия агента":"Выполненные инструменты"} · {m.reply.trace.length}</summary><ol>{m.reply.trace.map((t,index)=><li key={index}><span className={t.status==="ok"?"trace-ok":"trace-fail"}><Icon name={t.status==="ok"?"check":"close"} size={13}/></span><div>{toolLabels[t.tool]||t.tool}<code>{t.tool}</code></div><small>{t.ms} мс</small></li>)}</ol><small>{m.reply.elapsed_ms} мс всего</small></details><div className={`response-mode ${m.reply.mode}`}>{m.reply.mode==="agent"?"AI + проверенные данные":m.reply.mode==="fallback"?"Резервный локальный ответ":"Локальный ответ · без LLM"}</div>{m.reply.mode==="fallback"&&<p className="tiny muted">{m.reply.notice}</p>}</>}</div>)}
        {busy&&<div className="agent-working" role="status"><span className="working-dots"><i/><i/><i/></span>Проверяю данные и следующий шаг…</div>}<div ref={messagesEnd}/>
      </div>
      <div className="agent-input-area"><div className="quick-commands">{questions.map(q=><button key={q} disabled={busy||loading} onClick={()=>ask(q)}>{q}</button>)}</div><form className="chat-composer" onSubmit={(e:FormEvent)=>{e.preventDefault();ask(input);}}><label className="sr-only" htmlFor="agent-input">Сообщение агенту</label><textarea id="agent-input" placeholder={hr?"Спроси о развитии команды…":"Что поможет мне расти?"} value={input} maxLength={2000} rows={2} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();ask(input);}}}/><div><span>Enter — отправить</span><button aria-label="Отправить сообщение" disabled={busy||loading||!input.trim()}><Icon name="up" size={19}/></button></div></form><span className="agent-privacy"><Icon name="shield" size={12}/>Доступ только в пределах вашей роли</span></div>
    </aside>
    {confirmation&&<div className="modal-backdrop" onClick={()=>{if(!busy)setConfirmation(null);}}><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="complete-title" onClick={e=>e.stopPropagation()}><span className="achievement-medal"><Icon name="flag" size={28}/></span><h2 id="complete-title">Квест действительно выполнен?</h2><h3>{confirmation.title}</h3><p>Отметка сохранится в истории и обновит ожидаемый прогресс. Подтверждённая оценка навыков и грейд останутся прежними.</p><div className="dialog-actions"><button autoFocus className="button" disabled={busy} onClick={()=>setConfirmation(null)}>Ещё прохожу</button><button className="button primary" disabled={busy} onClick={complete}>{busy?"Сохраняем…":"Да, выполнен"}</button></div></section></div>}
  </div>;
}
