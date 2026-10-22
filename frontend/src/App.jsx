import { useCallback, useEffect, useState } from "react";
import { api, download, elder, getToken, setToken } from "./api";
import { I18nProvider, LANGUAGES, LanguagePicker, translate, useI18n } from "./i18n.jsx";

const LEVELS = ["Normal", "Low", "Medium", "High", "Critical"];   // codes stay English: they drive the colours
const KINDS = ["medication", "meal", "water", "activity"];

function Login({ onDone }) {
  const { t } = useI18n();
  const [f, setF] = useState({ username: "", password: "" });
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try { const r = await api("/auth/login", "POST", f); setToken(r.token); onDone(r.user); }
    catch (x) { setErr(x.message.includes("fetch") ? t("auth.failed") : x.message); }
  };
  return (
    <form className="login" onSubmit={submit}>
      <h1>{t("auth.signin_title")}</h1>
      <p>{t("auth.signin_sub")}</p>
      <input placeholder={t("auth.username")} value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
      <input type="password" placeholder={t("auth.password")} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
      {err && <p className="error" role="alert">{err}</p>}
      <button type="submit">{t("auth.signin")}</button>
      <LanguagePicker />
    </form>
  );
}

function Dashboard({ me }) {
  const { t, fmt } = useI18n();
  const [people, setPeople] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [plan, setPlan] = useState([]);
  const [form, setForm] = useState({ kind: "medication", title: "", time: "09:00" });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setPeople(await api("/elderly")); setAlerts(await api("/alerts"));
      if (sel) { setDetail(await api(`/elderly/${sel}`)); setPlan(await api(`/elderly/${sel}/careplan`)); }
      setError("");
    } catch (x) { setError(x.message); }
  }, [sel]);
  useEffect(() => { load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, [load]);

  const act = async (fn) => { try { await fn(); } catch (x) { setError(x.message); } load(); };
  const counts = LEVELS.map((l) => people.filter((p) => p.level === l).length);
  const open = alerts.filter((a) => a.status === "open");
  const level = (l) => t("level." + l);

  return (
    <>
      <div className="top">
        <p>{t("dash.monitored", { n: people.length, open: open.length })}</p>
        {me.role === "admin" && <button onClick={() => act(() => api("/simulate/seed", "POST"))}>{t("dash.load_sample")}</button>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="bar">{LEVELS.map((l, i) => counts[i] > 0 && <div key={l} data-level={l} style={{ flex: counts[i] }}>{counts[i]}</div>)}</div>
      <ul className="legend">{LEVELS.map((l, i) => <li key={l} data-level={l}>{level(l)}: {counts[i]}</li>)}</ul>
      <main>
        <section>
          <h2>{t("dash.attention")}</h2>
          {people.length === 0 && <p className="empty">{t(me.role === "admin" ? "dash.empty_admin" : "dash.empty_caregiver")}</p>}
          <ul className="people">{people.map((p) => (
            <li key={p.id}><button className={sel === p.id ? "row on" : "row"} onClick={() => setSel(p.id)} data-level={p.level}>
              <span className="dot" /><span className="name">{p.name}<small>{p.age ? t("dash.age", { n: p.age }) : ""}</small></span><span className="lvl">{level(p.level)}</span>
            </button></li>))}
          </ul>
        </section>
        <section>
          {detail ? (
            <div className="detail" data-level={detail.risk.level}>
              <h2>{detail.name}</h2>
              <p className="big">{t("dash.risk", { level: level(detail.risk.level) })} <small>{t("dash.score", { n: detail.risk.score })}</small></p>
              <h3>{t("dash.why")}</h3>
              {detail.risk.reasons.length ? <ul>{detail.risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : <p>{t("dash.nothing")}</p>}
              {detail.risk.model && (
                <p className="note">{t("dash.model", { pct: Math.round(detail.risk.model.probability * 100) })}
                  {detail.risk.model.top_factors.length > 0 && t("dash.model_factors", { factors: detail.risk.model.top_factors.join(", ") })}
                  {detail.risk.model.safety_floor && t("dash.model_safety", { level: level(detail.risk.model.safety_floor) })}.</p>)}
              {detail.risk.next_step && <p className="next">{t("dash.next", { step: detail.risk.next_step })}</p>}
              <p>{t("dash.checkin_delay", { n: detail.risk.signals.checkin_delay_min })}
                {detail.risk.signals.checkin_usual_min != null && t("dash.checkin_usual", { n: detail.risk.signals.checkin_usual_min })}. {t("dash.baseline", { n: detail.baseline_activity })}</p>
              <p className="note">{t("dash.screen")} <b>/#/elder</b> {t("dash.screen_code")} <b>{detail.access_code}</b>.</p>
              <div className="actions">
                <button onClick={() => act(() => api(`/elderly/${detail.id}/checkin`, "POST"))}>{t("dash.record_checkin")}</button>
                <button onClick={() => act(() => api("/events", "POST", { elderly_id: detail.id, kind: "fall" }))}>{t("dash.simulate_fall")}</button>
                <button onClick={() => act(() => api("/events", "POST", { elderly_id: detail.id, kind: "ok" }))}>{t("dash.im_ok")}</button>
              </div>
              <h3>{t("dash.risk_changes")}</h3>
              <ul className="hist">{detail.history.map((h, i) => <li key={i} data-level={h.level}><b>{level(h.level)}</b> <small>{fmt(h.at)}</small></li>)}</ul>
              <h3>{t("dash.careplan")}</h3>
              <p className="note">{t("dash.careplan_note")}</p>
              {plan.length === 0 && <p className="empty">{t("dash.no_items")}</p>}
              <ul className="plan">{plan.map((i) => (
                <li key={i.id} className={i.done_today ? "done" : i.overdue ? "overdue" : ""}>
                  <label><input type="checkbox" checked={i.done_today} onChange={() => act(() => api(`/careplan/${i.id}/done`, "POST"))} />
                    <span className="t">{i.time}</span> {i.title} <small>{t("dash.plan_kind", { kind: t("kind." + i.kind) })}</small>{i.overdue && <strong className="od"> {t("dash.overdue")}</strong>}</label>
                  <button aria-label={t("dash.remove", { title: i.title })} onClick={() => act(() => api(`/careplan/${i.id}`, "DELETE"))}>{t("dash.remove_btn")}</button>
                </li>))}
              </ul>
              <form className="add" onSubmit={(e) => { e.preventDefault(); if (!form.title.trim()) return;
                act(() => api(`/elderly/${detail.id}/careplan`, "POST", form)); setForm({ ...form, title: "" }); }}>
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} aria-label={t("dash.type")}>
                  {KINDS.map((k) => <option key={k} value={k}>{t("kind." + k)}</option>)}
                </select>
                <input type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} aria-label={t("dash.time")} />
                <input placeholder={t("dash.what")} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} aria-label={t("dash.what")} />
                <button type="submit">{t("dash.add_reminder")}</button>
              </form>
            </div>
          ) : <p className="empty">{t("dash.select_person")}</p>}
          <h2>{t("dash.alerts")}</h2>
          {alerts.length === 0 && <p className="empty">{t("dash.no_alerts")}</p>}
          <ul className="alerts">{alerts.map((a) => (
            <li key={a.id} data-level={a.level} className={a.status}>
              <div><strong>{a.name}</strong> {level(a.level)}: {a.reasons}
                {a.status === "open" && <div className="steps" aria-label={t("dash.step_aria", { n: a.stage })}>
                  {[1, 2, 3, 4].map((n) => <i key={n} className={n <= a.stage ? "on" : ""} />)}<span>{t("dash.step", { n: a.stage, text: a.stage_text })}</span></div>}
              </div>
              {a.status === "open" ? <button onClick={() => act(() => api(`/alerts/${a.id}/ack`, "POST"))}>{t("dash.acknowledge")}</button>
                : <em>{t("status." + a.status)}{a.resolved_by ? " " + t("dash.by", { who: t("by." + a.resolved_by) }) : ""}</em>}
            </li>))}
          </ul>
        </section>
      </main>
    </>
  );
}

function Analytics() {
  const { t } = useI18n();
  const [d, setD] = useState(null);
  const [info, setInfo] = useState(null);
  useEffect(() => { api("/analytics").then(setD).catch(() => {}); api("/model/info").then(setInfo).catch(() => {}); }, []);
  if (!d) return <p className="empty">{t("ana.loading")}</p>;
  const days = Object.entries(d.alerts_per_day), max = Math.max(1, ...days.map(([, n]) => n));
  const hmax = Math.max(1, ...d.falls_by_hour);
  const on = (v) => t(v ? "ana.active" : "ana.off");
  return (
    <section>
      <h2>{t("ana.title")}</h2>
      <p>{t("ana.summary", { alerts: d.total_alerts, falls: d.falls, late: d.checkin_failures, resp: d.avg_response_min ?? t("ana.no_data") })}</p>
      <p>{d.false_alarm_rate == null ? t("ana.no_data") : t("ana.false_alarm", { rate: d.false_alarm_rate })} <small>{t("ana.false_alarm_note")}</small></p>
      <h3>{t("ana.per_day")}</h3>
      <div className="chart">{days.map(([day, n]) => (
        <div key={day}><span>{n}</span><i style={{ height: `${(n / max) * 120}px` }} /><small>{day.slice(5)}</small></div>))}
      </div>
      <h3>{t("ana.by_hour")}</h3>
      <div className="chart thin">{d.falls_by_hour.map((n, h) => (
        <div key={h}><i style={{ height: `${(n / hmax) * 100}px` }} title={t("ana.falls", { n })} /><small>{h}</small></div>))}
      </div>
      <h3>{t("ana.models")}</h3>
      {info && info.metrics ? (
        <ul>
          <li>{t("ana.risk_model", { state: on(info.risk_model_active), auc: info.metrics.risk.auc.model, rules: info.metrics.risk.auc.rules })}</li>
          <li>{t("ana.pose_model", { state: on(info.pose_model_active), acc: Math.round(info.metrics.pose.model_accuracy * 100), rules: Math.round(info.metrics.pose.rules_accuracy * 100) })}</li>
          <li>{t("ana.anomaly", { f1: info.metrics.anomaly.personal_baseline.f1, all: info.metrics.anomaly.population_threshold.f1 })}</li>
        </ul>
      ) : <p className="empty">{t("ana.no_models")}</p>}
      <p className="note">{t("ana.note")}</p>
      <h3>{t("ana.export")}</h3>
      <div className="actions">{["alerts", "risk", "events", "checkins", "careplan", "people"].map((n) =>
        <button key={n} onClick={() => download(n)}>{n}.csv</button>)}</div>
      <p className="note">{t("ana.export_note")}</p>
    </section>
  );
}

function Notifications() {
  const { t, fmt } = useI18n();
  const [rows, setRows] = useState([]);
  useEffect(() => { const f = () => api("/notifications").then(setRows).catch(() => {}); f(); const timer = setInterval(f, 5000); return () => clearInterval(timer); }, []);
  return (
    <section>
      <h2>{t("notif.title")}</h2>
      {rows.length === 0 && <p className="empty">{t("notif.empty")}</p>}
      <ul className="alerts">{rows.map((n) => <li key={n.id} data-level="High"><div>{n.text}<small className="when">{fmt(n.at)}</small></div></li>)}</ul>
    </section>
  );
}

function Admin() {
  const { t } = useI18n();
  const [users, setUsers] = useState([]);
  const [people, setPeople] = useState([]);
  const [msg, setMsg] = useState("");
  const [u, setU] = useState({ username: "", password: "", email: "", telegram_chat_id: "" });
  const [p, setP] = useState({ name: "", age: "", checkin_time: "09:00", emergency_contact: "", caregiver_id: "" });
  const load = useCallback(async () => { setUsers(await api("/users")); setPeople(await api("/admin/people")); }, []);
  useEffect(() => { load().catch((x) => setMsg(x.message)); }, [load]);
  const run = async (fn, ok) => { try { await fn(); setMsg(ok); await load(); return true; } catch (x) { setMsg(x.message); return false; } };
  const cgs = users.filter((x) => x.role === "caregiver");
  const nameOf = (id) => users.find((x) => x.id === id)?.username;
  const field = (obj, set, key, props) => <input value={obj[key]} onChange={(e) => set({ ...obj, [key]: e.target.value })} {...props} />;
  return (
    <section className="admin">
      <h2>{t("admin.title")}</h2>
      {msg && <p className="note" role="status">{msg}</p>}
      <h3>{t("admin.add_caregiver")}</h3>
      <form className="add" onSubmit={async (e) => { e.preventDefault();
        const ok = await run(() => api("/users", "POST", { username: u.username.trim(), password: u.password,
          email: u.email || null, telegram_chat_id: u.telegram_chat_id || null }), t("admin.caregiver_added", { name: u.username }));
        if (ok) setU({ username: "", password: "", email: "", telegram_chat_id: "" }); }}>
        {field(u, setU, "username", { placeholder: t("admin.username"), required: true })}
        {field(u, setU, "password", { type: "password", placeholder: t("admin.password"), required: true })}
        {field(u, setU, "email", { type: "email", placeholder: t("admin.email") })}
        {field(u, setU, "telegram_chat_id", { placeholder: t("admin.telegram") })}
        <button type="submit">{t("admin.add_caregiver_btn")}</button>
      </form>
      <p className="note">{t("admin.caregivers", { list: cgs.length ? cgs.map((c) => c.username).join(", ") : t("admin.none_yet") })}</p>

      <h3>{t("admin.add_person")}</h3>
      <form className="add" onSubmit={async (e) => { e.preventDefault();
        const ok = await run(() => api("/elderly", "POST", { name: p.name.trim(), age: p.age ? Number(p.age) : null, checkin_time: p.checkin_time,
          emergency_contact: p.emergency_contact, caregiver_id: p.caregiver_id ? Number(p.caregiver_id) : null }), t("admin.person_added", { name: p.name }));
        if (ok) setP({ ...p, name: "", age: "", emergency_contact: "" }); }}>
        {field(p, setP, "name", { placeholder: t("admin.full_name"), required: true })}
        {field(p, setP, "age", { type: "number", min: "0", placeholder: t("admin.age") })}
        {field(p, setP, "checkin_time", { type: "time", "aria-label": t("admin.checkin_time") })}
        {field(p, setP, "emergency_contact", { placeholder: t("admin.emergency") })}
        <select value={p.caregiver_id} onChange={(e) => setP({ ...p, caregiver_id: e.target.value })} aria-label={t("admin.caregiver")}>
          <option value="">{t("admin.no_caregiver")}</option>{cgs.map((c) => <option key={c.id} value={c.id}>{c.username}</option>)}
        </select>
        <button type="submit">{t("admin.add_person_btn")}</button>
      </form>

      <h3>{t("admin.who")}</h3>
      {people.length === 0 && <p className="empty">{t("admin.no_people")}</p>}
      <ul className="plan">{people.map((x) => (
        <li key={x.id}><span>{x.name} <small>{t("admin.meta", { age: x.age ? t("dash.age", { n: x.age }) : "", code: x.access_code })}</small></span>
          <select value={x.caregiver_id ?? ""} aria-label={t("admin.caregiver_for", { name: x.name })}
            onChange={(e) => run(() => api(`/elderly/${x.id}/assign`, "PUT", { caregiver_id: e.target.value ? Number(e.target.value) : null }),
              t("admin.assigned", { name: x.name, who: e.target.value ? nameOf(Number(e.target.value)) : t("admin.no_one") }))}>
            <option value="">{t("admin.not_assigned")}</option>{cgs.map((c) => <option key={c.id} value={c.id}>{c.username}</option>)}
          </select></li>))}
      </ul>
    </section>
  );
}

function Settings() {
  const { t, lang, setLang } = useI18n();
  const [msg, setMsg] = useState("");
  const change = async (code) => {
    setLang(code);   // the screen switches at once, then we remember it on the account too
    const label = LANGUAGES.find((l) => l.code === code).label;
    try { await api("/auth/lang", "PUT", { lang: code }); setMsg(translate(code, "settings.saved", { lang: label })); }
    catch (x) { setMsg(translate(code, "settings.failed", { error: x.message })); }
  };
  return (
    <section className="settings">
      <h2>{t("settings.title")}</h2>
      <h3>{t("settings.language")}</h3>
      <p className="note">{t("settings.language_note")}</p>
      <div className="langs" role="group" aria-label={t("settings.language")}>
        {LANGUAGES.map((l) => <button key={l.code} type="button" className={l.code === lang ? "tab on" : "tab"} aria-pressed={l.code === lang}
          onClick={() => change(l.code)}>{l.label}</button>)}
      </div>
      <p className="note"><b>{t("settings.preview")}</b> {t("settings.sample")}</p>
      {msg && <p className="note" role="status">{msg}</p>}
    </section>
  );
}

function ElderApp() {
  const { t, fmt } = useI18n();
  const [code, setCode] = useState(localStorage.getItem("elder_code") || "");
  const [typed, setTyped] = useState("");
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    if (!code) return;
    try { setD(await elder("/elder/me", code)); setErr(""); }
    catch (x) { if (x.message === "Wrong code" || x.message.length === 0) { localStorage.removeItem("elder_code"); setCode(""); } setErr(x.message); }
  }, [code]);
  useEffect(() => { load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, [load]);
  const act = async (path) => { try { await elder(path, code, "POST"); } catch (x) { setErr(x.message); } load(); };
  const help = () => { if (window.confirm(t("elder.help_confirm"))) act("/elder/help"); };

  if (!code) return (
    <form className="elder" onSubmit={(e) => { e.preventDefault(); localStorage.setItem("elder_code", typed.trim()); setCode(typed.trim()); }}>
      <LanguagePicker className="elder-lang" />
      <h1>ElderLife</h1>
      <p>{t("elder.code")}</p>
      <input className="code" inputMode="numeric" maxLength={6} value={typed} onChange={(e) => setTyped(e.target.value)} aria-label={t("elder.your_code")} />
      {err && <p className="error" role="alert">{err}</p>}
      <button className="big-btn" type="submit">{t("elder.continue")}</button>
    </form>
  );
  if (!d) return <div className="elder"><LanguagePicker className="elder-lang" /><p>{err || t("elder.loading")}</p></div>;
  return (
    <div className="elder">
      <LanguagePicker className="elder-lang" />
      <h1>{t("elder.hello", { name: d.name })}</h1>
      {err && <p className="error" role="alert">{err}</p>}
      {d.prompt && (
        <div className="banner" role="alert"><h2>{t("elder.ok_title")}</h2>
          <button className="big-btn ok-btn" onClick={() => act("/elder/ok")}>{t("elder.yes_ok")}</button></div>
      )}
      {d.checkin_due
        ? <button className="big-btn ok-btn" onClick={() => act("/elder/checkin")}>{t("elder.checkin")}</button>
        : <p className="done-msg">{t("elder.checked_in")}</p>}
      <h2>{t("elder.today")}</h2>
      <ul className="plan big">{d.plan.map((i) => (
        <li key={i.id} className={i.done_today ? "done" : i.overdue ? "overdue" : ""}>
          <label><input type="checkbox" checked={i.done_today} onChange={() => act(`/elder/done/${i.id}`)} />
            <span className="t">{i.time}</span> {i.title}</label></li>))}
      </ul>
      <button className="big-btn help-btn" onClick={help}>{t("elder.help")}</button>
      <p className="note"><a href="#/elder" onClick={() => { localStorage.removeItem("elder_code"); setCode(""); }}>{t("elder.different_code")}</a></p>
    </div>
  );
}

function Main() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState("dashboard");
  useEffect(() => {
    if (getToken()) api("/auth/me").then(setMe).catch(() => {});
    const out = () => setMe(null); window.addEventListener("logout", out); return () => window.removeEventListener("logout", out);
  }, []);
  if (!me) return <div className="app"><Login onDone={setMe} /></div>;
  const tabs = [["dashboard", "nav.dashboard"], ["analytics", "nav.analytics"], ["notifications", "nav.notifications"],
    ...(me.role === "admin" ? [["admin", "nav.admin"]] : []), ["settings", "nav.settings"]];
  return (
    <div className="app">
      <header>
        <h1>{t("app.name")}</h1>
        <nav>{tabs.map(([k, l]) =>
          <button key={k} className={tab === k ? "tab on" : "tab"} onClick={() => setTab(k)}>{t(l)}</button>)}</nav>
        <span>{t("auth.user", { name: me.username, role: t("role." + me.role) })}</span>
        <button onClick={() => { setToken(null); setMe(null); }}>{t("auth.signout")}</button>
      </header>
      {tab === "dashboard" && <Dashboard me={me} />}
      {tab === "analytics" && <Analytics />}
      {tab === "notifications" && <Notifications />}
      {tab === "admin" && me.role === "admin" && <Admin />}
      {tab === "settings" && <Settings />}
    </div>
  );
}

export default function App() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const f = () => setHash(window.location.hash);
    window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f);
  }, []);
  return <I18nProvider>{hash.startsWith("#/elder") ? <ElderApp /> : <Main />}</I18nProvider>;
}
