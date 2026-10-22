import os, io, csv, hmac, json, time, base64, hashlib, random, smtplib, threading, urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from email.message import EmailMessage
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .risk import assess, NEXT_STEP, ml_enabled
from .vision import classify_auto, POINTS, ACTIVITY_LEVEL, POSE_MODELS
from .mlmodels import load_json
from . import i18n
from .i18n import tr

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./elderlife4.db")
SECRET = os.getenv("SECRET_KEY", "dev-secret-change-me")
DEVICE_KEY = os.getenv("DEVICE_KEY", "dev-key")          # used by AI services / cameras posting events
STEP = max(1, int(os.getenv("ESCALATION_STEP_SECONDS", "30")))   # seconds between escalation stages (demo value)
VERIFY_S = int(os.getenv("VERIFY_SECONDS", "60"))        # time the person has to answer "Are you okay?" after a fall
FALL_MIN_CONF = float(os.getenv("FALL_MIN_CONFIDENCE", "0.6"))   # falls below this confidence are ignored
SNOOZE_MIN = int(os.getenv("ACK_SNOOZE_MINUTES", "30"))  # no new alert for a person after an acknowledgement
TG = os.getenv("TELEGRAM_BOT_TOKEN")
SMTP_HOST, SMTP_PORT = os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587"))
SMTP_USER, SMTP_PASS = os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "elderlife@localhost")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
now = datetime.now  # all timestamps use server local time

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    salt = Column(String); pw = Column(String)
    role = Column(String, default="caregiver")  # admin | caregiver
    telegram_chat_id = Column(String, nullable=True)
    email = Column(String, nullable=True)
    lang = Column(String, default="en")         # language of the email/Telegram alerts this user receives

class Elderly(Base):
    __tablename__ = "elderly"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False); age = Column(Integer)
    baseline_activity = Column(Float, default=50)
    checkin_time = Column(String, default="09:00")
    caregiver_id = Column(Integer, nullable=True)
    emergency_contact = Column(String, default="")
    access_code = Column(String, unique=True)           # opens the person's own screen
    silenced_at = Column(DateTime, nullable=True); silenced_until = Column(DateTime, nullable=True)

class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True); elderly_id = Column(Integer, index=True)
    scheduled_at = Column(DateTime); responded_at = Column(DateTime, nullable=True)

class Event(Base):  # kind: activity | fall (value = confidence) | ok | sos
    __tablename__ = "events"
    id = Column(Integer, primary_key=True); elderly_id = Column(Integer, index=True)
    kind = Column(String); value = Column(Float, default=0); created_at = Column(DateTime, default=now)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True); elderly_id = Column(Integer, index=True)
    level = Column(String); reasons = Column(String)
    status = Column(String, default="open")  # open | acknowledged | resolved
    stage = Column(Integer, default=1)
    resolved_by = Column(String, nullable=True)  # person | caregiver
    created_at = Column(DateTime, default=now); resolved_at = Column(DateTime, nullable=True)

class CarePlanItem(Base):  # reminders only: recorded plan, no diagnosis or dose changes
    __tablename__ = "careplan"
    id = Column(Integer, primary_key=True); elderly_id = Column(Integer, index=True)
    kind = Column(String); title = Column(String); time = Column(String)
    note = Column(String, default=""); done_date = Column(String, nullable=True)

class RiskLog(Base):
    __tablename__ = "risklog"
    id = Column(Integer, primary_key=True); elderly_id = Column(Integer, index=True)
    level = Column(String); score = Column(Float); created_at = Column(DateTime, default=now)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True); user_id = Column(Integer, nullable=True)
    alert_id = Column(Integer); text = Column(String); created_at = Column(DateTime, default=now)

Base.metadata.create_all(engine)

def ensure_columns(table, columns):   # tiny migration for databases created by an older version
    have = {c["name"] for c in inspect(engine).get_columns(table)}
    with engine.begin() as conn:
        for name, ddl in columns.items():
            if name not in have: conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

ensure_columns("users", {"lang": "VARCHAR(8) DEFAULT 'en'"})

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def lang_of(request: Request) -> str:
    """The language this request wants, from Accept-Language (set by the frontend Settings screen)."""
    return i18n.negotiate(request.headers.get("accept-language"))

# ---------- auth (stdlib only) ----------
def hash_pw(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
def new_user(db, username, pw, role="caregiver", tg=None, email=None):
    salt = os.urandom(8).hex()
    u = User(username=username, salt=salt, pw=hash_pw(pw, salt), role=role, telegram_chat_id=tg, email=email)
    db.add(u); db.commit(); return u
def make_token(uid):
    p = f"{uid}:{int(time.time()) + 86400}"
    sig = hmac.new(SECRET.encode(), p.encode(), "sha256").hexdigest()
    return base64.urlsafe_b64encode(f"{p}:{sig}".encode()).decode()
def read_token(tok):
    try:
        uid, exp, sig = base64.urlsafe_b64decode(tok.encode()).decode().split(":")
        ok = hmac.compare_digest(sig, hmac.new(SECRET.encode(), f"{uid}:{exp}".encode(), "sha256").hexdigest())
        return int(uid) if ok and int(exp) > time.time() else None
    except Exception: return None
def current_user(authorization: str = Header(None), db=Depends(get_db)):
    if authorization and authorization.startswith("Bearer "):
        uid = read_token(authorization[7:]); u = db.get(User, uid) if uid else None
        if u: return u
    raise HTTPException(401, "Please log in")
def ingest_auth(authorization: str = Header(None), x_device_key: str = Header(None), db=Depends(get_db)):
    return None if x_device_key == DEVICE_KEY else current_user(authorization, db)
def admin_only(u=Depends(current_user)):
    if u.role != "admin": raise HTTPException(403, "Admins only")
    return u
def elder_auth(x_elder_code: str = Header(None), db=Depends(get_db)):
    e = db.query(Elderly).filter_by(access_code=x_elder_code).first() if x_elder_code else None
    if not e: raise HTTPException(401, "Wrong code")
    return e
def my_people(db, u):
    q = db.query(Elderly); return q if u.role == "admin" else q.filter(Elderly.caregiver_id == u.id)
def person(db, u, eid):
    e = my_people(db, u).filter(Elderly.id == eid).first()
    if not e: raise HTTPException(404, "Person not found")
    return e
def target_person(db, u, eid):  # u is None for trusted devices (camera / AI service)
    if u: return person(db, u, eid)
    e = db.get(Elderly, eid)
    if not e: raise HTTPException(404, "Person not found")
    return e
def new_code(db):
    while True:
        c = f"{random.randint(100000, 999999)}"
        if not db.query(Elderly).filter_by(access_code=c).first(): return c

# ---------- risk signals ----------
def is_overdue(i, grace=30):
    t = datetime.now()
    if i.done_date == t.strftime("%Y-%m-%d"): return False
    h, m = map(int, i.time.split(":"))
    return t > t.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(minutes=grace)

def signals(db, e):
    t = now()
    ci = db.query(CheckIn).filter_by(elderly_id=e.id).order_by(CheckIn.scheduled_at.desc()).first()
    delay = max(0, ((ci.responded_at or t) - ci.scheduled_at).total_seconds() / 60) if ci else 0
    past = [c for c in db.query(CheckIn).filter(CheckIn.elderly_id == e.id, CheckIn.responded_at != None)
            .order_by(CheckIn.scheduled_at.desc()).limit(8).all() if not ci or c.id != ci.id]
    ds = sorted((c.responded_at - c.scheduled_at).total_seconds() / 60 for c in past)
    usual = ds[len(ds) // 2] if len(ds) >= 3 else None      # the person's usual check-in delay (median)
    acts = [x.value for x in db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "activity", Event.created_at > t - timedelta(hours=3))]
    ratio = (sum(acts) / len(acts)) / e.baseline_activity if acts else None
    falls = [x for x in db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "fall", Event.created_at > t - timedelta(hours=2))
             .order_by(Event.created_at.desc()) if (x.value or 1.0) >= FALL_MIN_CONF]   # low-confidence falls are ignored
    fall = falls[0] if falls else None
    answered = bool(fall and db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "ok", Event.created_at > fall.created_at).first())
    sos = db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "sos", Event.created_at > t - timedelta(hours=1)).order_by(Event.created_at.desc()).first()
    sos_on = bool(sos and not db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "ok", Event.created_at > sos.created_at).first())
    missed = sum(is_overdue(i) for i in db.query(CarePlanItem).filter_by(elderly_id=e.id))
    return {"checkin_delay_min": round(delay), "checkin_responded": bool(ci and ci.responded_at),
            "checkin_usual_min": round(usual) if usual is not None else None, "activity_ratio": ratio,
            "fall": bool(fall), "fall_answered": answered, "fall_age_s": (t - fall.created_at).total_seconds() if fall else 0,
            "verify_s": VERIFY_S, "sos": sos_on, "missed_reminders": missed,
            "fall_conf": ((fall.value or 1.0) if fall else 0.0), "age": e.age or 78, "hour": t.hour}

def snoozed(db, e):
    if not (e.silenced_until and now() < e.silenced_until): return False
    return not db.query(Event).filter(Event.elderly_id == e.id, Event.kind.in_(["fall", "sos"]), Event.created_at > e.silenced_at).first()

def evaluate(db, e):
    s = signals(db, e); r = assess(s)
    last = db.query(RiskLog).filter_by(elderly_id=e.id).order_by(RiskLog.id.desc()).first()
    if not last or last.level != r["level"]:
        db.add(RiskLog(elderly_id=e.id, level=r["level"], score=r["score"])); db.commit()
    if r["level"] in ("High", "Critical"):
        reasons = i18n.reasons_to_json(r["reason_codes"])   # stored as keys, translated when read
        a = db.query(Alert).filter_by(elderly_id=e.id, status="open").first()
        if a: a.level, a.reasons = r["level"], reasons
        elif not snoozed(db, e): db.add(Alert(elderly_id=e.id, level=r["level"], reasons=reasons, stage=1))
        db.commit()
    return {**r, "next_step": NEXT_STEP.get(r["level"]), "signals": s}

def close_alerts(db, e, by):  # by: "person" (answered "I'm OK") or "caregiver" (acknowledged)
    for a in db.query(Alert).filter_by(elderly_id=e.id, status="open").all():
        a.status = "resolved" if by == "person" else "acknowledged"; a.resolved_at = now(); a.resolved_by = by
    e.silenced_at = now(); e.silenced_until = now() + timedelta(minutes=SNOOZE_MIN)

# ---------- notifications ----------
def send_email(to, subject, text):
    if not (SMTP_HOST and to): return
    try:
        m = EmailMessage(); m["From"], m["To"], m["Subject"] = SMTP_FROM, to, subject; m.set_content(text)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            if SMTP_USER: s.login(SMTP_USER, SMTP_PASS)
            s.send_message(m)
    except Exception as ex: print("email failed:", ex)

def notify(db, a):
    """Store the notification as a key + parameters, then send it in the caregiver's own language."""
    e = db.get(Elderly, a.elderly_id); cg = db.get(User, e.caregiver_id) if e and e.caregiver_id else None
    codes = i18n.load_reasons(a.reasons) or []
    payload = ({"key": "notif.risk", "params": {"name": e.name, "level": a.level, "reason_codes": codes}} if a.stage <= 3
               else {"key": "notif.emergency", "params": {"name": e.name, "contact": e.emergency_contact or "", "reason_codes": codes}})
    cg_lang = (cg.lang if cg and cg.lang else i18n.DEFAULT_LANG)
    text = i18n.render_notification(json.dumps(payload, ensure_ascii=False), cg_lang)
    db.add(Notification(user_id=cg.id if cg else None, alert_id=a.id, text=json.dumps(payload, ensure_ascii=False))); db.commit()
    if cg:
        send_email(cg.email, tr("notif.subject", cg_lang, name=e.name), text)
        if TG and cg.telegram_chat_id:
            try:
                urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TG}/sendMessage",
                    data=json.dumps({"chat_id": cg.telegram_chat_id, "text": text}).encode(),
                    headers={"Content-Type": "application/json"}), timeout=5)
            except Exception as ex: print("telegram failed:", ex)

# ---------- background: escalation, daily check-ins, baselines ----------
def tick(db, update_baselines=False):
    t = now()
    for a in db.query(Alert).filter_by(status="open").all():
        target = min(4, 1 + int((t - a.created_at).total_seconds() // STEP))
        while a.stage < target:
            a.stage += 1
            if a.stage >= 3: notify(db, a)
    midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
    for e in db.query(Elderly).all():
        h, m = map(int, e.checkin_time.split(":")); sched = t.replace(hour=h, minute=m, second=0, microsecond=0)
        if t >= sched and not db.query(CheckIn).filter(CheckIn.elderly_id == e.id, CheckIn.scheduled_at >= midnight).first():
            db.add(CheckIn(elderly_id=e.id, scheduled_at=sched))
        if update_baselines:  # personal baseline = mean activity of older history (not the last 3 hours)
            old = [x.value for x in db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "activity",
                   Event.created_at < t - timedelta(hours=3), Event.created_at > t - timedelta(days=7))]
            if len(old) >= 5: e.baseline_activity = round(sum(old) / len(old), 1)
    db.commit()

@asynccontextmanager
async def lifespan(app):
    db = SessionLocal()
    if not db.query(User).first(): new_user(db, "admin", "admin123", "admin")
    db.close()
    def loop():
        n = 0
        while True:
            try:
                d = SessionLocal(); tick(d, n % 6 == 0); d.close()
            except Exception as ex: print("tick error:", ex)
            n += 1; time.sleep(10)
    threading.Thread(target=loop, daemon=True).start()
    yield

app = FastAPI(title="ElderLife AI API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def language(request: Request, call_next):
    """Remember the requested language on the request and translate API error messages."""
    request.state.lang = i18n.negotiate(request.headers.get("accept-language"))
    resp = await call_next(request)
    if resp.status_code < 400: return resp
    try:
        body = b"".join([chunk async for chunk in resp.body_iterator])
        data = json.loads(body)
    except Exception:
        return resp
    if not isinstance(data, dict) or not isinstance(data.get("detail"), str): return resp
    detail = i18n.translate_error(data["detail"], request.state.lang)
    if detail == data["detail"]: return resp
    data["detail"] = detail
    headers = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"}
    return JSONResponse(data, status_code=resp.status_code, headers=headers)

class Login(BaseModel): username: str; password: str
class LangIn(BaseModel): lang: str
class NewUser(BaseModel): username: str; password: str; telegram_chat_id: str | None = None; email: str | None = None
class NewElderly(BaseModel):
    name: str; age: int | None = None; baseline_activity: float = 50
    checkin_time: str = "09:00"; caregiver_id: int | None = None; emergency_contact: str = ""
class NewEvent(BaseModel): elderly_id: int; kind: str; value: float = 0
class NewItem(BaseModel): kind: str; title: str; time: str; note: str = ""
class Assign(BaseModel): caregiver_id: int | None = None
class Pose(BaseModel):
    elderly_id: int; keypoints: dict[str, list[float]]
    prev_keypoints: dict[str, list[float]] | None = None; dt_s: float | None = None

@app.get("/model/info")
def model_info(_=Depends(current_user)):
    """Which AI models are active and how they scored on the (synthetic) evaluation."""
    return {"risk_model_active": ml_enabled(), "pose_model_active": bool(POSE_MODELS) and os.getenv("ML_MODE", "auto") != "off",
            "metrics": load_json("metrics.json")}

@app.get("/health")
def health(): return {"status": "ok"}

# ---------- auth + users ----------
@app.post("/auth/login")
def login(b: Login, db=Depends(get_db)):
    u = db.query(User).filter_by(username=b.username).first()
    if not u or not hmac.compare_digest(u.pw, hash_pw(b.password, u.salt)): raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(u.id), "user": {"id": u.id, "username": u.username, "role": u.role, "lang": u.lang or i18n.DEFAULT_LANG}}
@app.get("/auth/me")
def me(u=Depends(current_user)): return {"id": u.id, "username": u.username, "role": u.role, "lang": u.lang or i18n.DEFAULT_LANG}
@app.get("/languages")
def languages(): return {"languages": list(i18n.SUPPORTED), "names": i18n.LANG_NAMES, "default": i18n.DEFAULT_LANG}
@app.put("/auth/lang")
def set_lang(b: LangIn, db=Depends(get_db), u=Depends(current_user)):
    """Language of the email/Telegram alerts this user receives (the screen language is chosen in Settings)."""
    if b.lang not in i18n.SUPPORTED: raise HTTPException(400, "Unsupported language")
    u.lang = b.lang; db.commit(); return {"ok": True, "lang": u.lang}
@app.post("/users")
def create_user(b: NewUser, db=Depends(get_db), _=Depends(admin_only)):
    if len(b.password) < 6: raise HTTPException(400, "Password must be at least 6 characters")
    if db.query(User).filter_by(username=b.username).first(): raise HTTPException(400, "Username already exists")
    return {"id": new_user(db, b.username, b.password, "caregiver", b.telegram_chat_id, b.email).id}
@app.get("/users")
def users(db=Depends(get_db), _=Depends(admin_only)):
    return [{"id": x.id, "username": x.username, "role": x.role, "email": x.email} for x in db.query(User)]
@app.get("/admin/people")
def admin_people(db=Depends(get_db), _=Depends(admin_only)):
    return [{"id": e.id, "name": e.name, "age": e.age, "caregiver_id": e.caregiver_id, "access_code": e.access_code} for e in db.query(Elderly)]
@app.put("/elderly/{eid}/assign")
def assign(eid: int, b: Assign, db=Depends(get_db), _=Depends(admin_only)):
    e = db.get(Elderly, eid)
    if not e: raise HTTPException(404, "Person not found")
    if b.caregiver_id and not db.get(User, b.caregiver_id): raise HTTPException(400, "Caregiver not found")
    e.caregiver_id = b.caregiver_id; db.commit(); return {"ok": True}

# ---------- people ----------
@app.get("/elderly")
def list_elderly(db=Depends(get_db), u=Depends(current_user), lang: str = Depends(lang_of)):
    out = []
    for e in my_people(db, u).all():
        r = evaluate(db, e)
        out.append({"id": e.id, "name": e.name, "age": e.age, "level": r["level"], "score": r["score"],
                    "reasons": i18n.reasons_list(r["reason_codes"], lang)})
    return sorted(out, key=lambda x: -x["score"])

@app.post("/elderly")
def create_elderly(b: NewElderly, db=Depends(get_db), u=Depends(current_user)):
    d = b.model_dump()
    if u.role != "admin": d["caregiver_id"] = u.id
    e = Elderly(**d, access_code=new_code(db)); db.add(e); db.flush()
    db.add(CheckIn(elderly_id=e.id, scheduled_at=now())); db.commit()
    return {"id": e.id, "access_code": e.access_code}

@app.get("/elderly/{eid}")
def get_elderly(eid: int, db=Depends(get_db), u=Depends(current_user), lang: str = Depends(lang_of)):
    e = person(db, u, eid)
    ev = db.query(Event).filter_by(elderly_id=eid).order_by(Event.created_at.desc()).limit(10).all()
    hist = db.query(RiskLog).filter_by(elderly_id=eid).order_by(RiskLog.id.desc()).limit(10).all()
    return {"id": e.id, "name": e.name, "age": e.age, "baseline_activity": e.baseline_activity, "access_code": e.access_code,
            "risk": localize_risk(evaluate(db, e), lang),
            "events": [{"kind": x.kind, "value": x.value, "at": x.created_at.isoformat()} for x in ev],
            "history": [{"level": x.level, "score": x.score, "at": x.created_at.isoformat()} for x in hist]}

def localize_risk(r, lang):
    """Translate the reasons, the next step and the model factors for the reader."""
    out = {**r, "reasons": i18n.reasons_list(r["reason_codes"], lang),
           "next_step": tr("next." + r["level"].lower(), lang) if r["level"] in ("Medium", "High", "Critical") else None}
    if r.get("model"): out["model"] = {**r["model"], "top_factors": i18n.factor_texts(r["model"].get("top_factor_keys"), lang)}
    return out

def do_checkin(db, eid):
    ci = db.query(CheckIn).filter_by(elderly_id=eid, responded_at=None).order_by(CheckIn.scheduled_at.desc()).first()
    if not ci: ci = CheckIn(elderly_id=eid, scheduled_at=now()); db.add(ci)
    ci.responded_at = now(); db.commit()

@app.post("/elderly/{eid}/checkin")
def checkin(eid: int, db=Depends(get_db), u=Depends(current_user)):
    person(db, u, eid); do_checkin(db, eid); return {"ok": True}

# ---------- events (AI services, camera, caregiver simulation) ----------
@app.post("/events")
def add_event(b: NewEvent, db=Depends(get_db), u=Depends(ingest_auth)):
    if b.kind not in ("activity", "fall", "ok", "sos"): raise HTTPException(400, "kind must be activity, fall, ok or sos")
    e = target_person(db, u, b.elderly_id)
    db.add(Event(**b.model_dump()))
    if b.kind == "ok": close_alerts(db, e, "person")
    db.commit(); return evaluate(db, e)

@app.post("/vision/pose")
def vision_pose(b: Pose, db=Depends(get_db), u=Depends(ingest_auth)):
    """Camera/CV service sends body keypoints only (never images). Returns the recognised activity."""
    e = target_person(db, u, b.elderly_id)
    missing = [p for p in POINTS if p not in b.keypoints]
    if missing: raise HTTPException(400, f"Missing keypoints: {', '.join(missing)}")
    act, conf, source = classify_auto(b.keypoints, b.prev_keypoints, b.dt_s)
    db.add(Event(elderly_id=e.id, kind="activity", value=ACTIVITY_LEVEL[act]))
    if act == "falling": db.add(Event(elderly_id=e.id, kind="fall", value=conf))
    db.commit(); return {"activity": act, "confidence": conf, "source": source, "risk": evaluate(db, e)}

# ---------- care plan ----------
def item_out(i):
    return {"id": i.id, "kind": i.kind, "title": i.title, "time": i.time, "note": i.note,
            "done_today": i.done_date == now().strftime("%Y-%m-%d"), "overdue": is_overdue(i)}
def item_for(db, u, iid):
    i = db.get(CarePlanItem, iid)
    if not i: raise HTTPException(404, "Item not found")
    person(db, u, i.elderly_id); return i

@app.get("/elderly/{eid}/careplan")
def get_plan(eid: int, db=Depends(get_db), u=Depends(current_user)):
    person(db, u, eid); return [item_out(i) for i in db.query(CarePlanItem).filter_by(elderly_id=eid).order_by(CarePlanItem.time)]
@app.post("/elderly/{eid}/careplan")
def add_item(eid: int, b: NewItem, db=Depends(get_db), u=Depends(current_user)):
    person(db, u, eid)
    if b.kind not in ("medication", "meal", "water", "activity"): raise HTTPException(400, "Invalid kind")
    db.add(CarePlanItem(elderly_id=eid, **b.model_dump())); db.commit(); return {"ok": True}
@app.post("/careplan/{iid}/done")
def mark_done(iid: int, db=Depends(get_db), u=Depends(current_user)):
    i = item_for(db, u, iid); today = now().strftime("%Y-%m-%d")
    i.done_date = None if i.done_date == today else today; db.commit(); return item_out(i)
@app.delete("/careplan/{iid}")
def delete_item(iid: int, db=Depends(get_db), u=Depends(current_user)):
    db.delete(item_for(db, u, iid)); db.commit(); return {"ok": True}

# ---------- the person's own screen (authenticated by their access code) ----------
@app.get("/elder/me")
def elder_me(e=Depends(elder_auth), db=Depends(get_db)):
    s = signals(db, e); ci = db.query(CheckIn).filter_by(elderly_id=e.id).order_by(CheckIn.scheduled_at.desc()).first()
    open_alert = db.query(Alert).filter_by(elderly_id=e.id, status="open").first()
    return {"name": e.name, "checkin_due": bool(ci and not ci.responded_at),
            "prompt": bool(open_alert) or (s["fall"] and not s["fall_answered"]),
            "plan": [item_out(i) for i in db.query(CarePlanItem).filter_by(elderly_id=e.id).order_by(CarePlanItem.time)]}
@app.post("/elder/checkin")
def elder_checkin(e=Depends(elder_auth), db=Depends(get_db)):
    do_checkin(db, e.id); return {"ok": True}
@app.post("/elder/ok")
def elder_ok(e=Depends(elder_auth), db=Depends(get_db)):
    db.add(Event(elderly_id=e.id, kind="ok")); close_alerts(db, e, "person"); do_checkin_if_due(db, e.id); db.commit()
    return {"ok": True}
def do_checkin_if_due(db, eid):  # answering "I'm OK" also counts as today's check-in when one is waiting
    ci = db.query(CheckIn).filter_by(elderly_id=eid, responded_at=None).order_by(CheckIn.scheduled_at.desc()).first()
    if ci: ci.responded_at = now()
@app.post("/elder/help")
def elder_help(e=Depends(elder_auth), db=Depends(get_db)):
    db.add(Event(elderly_id=e.id, kind="sos"))
    a = db.query(Alert).filter_by(elderly_id=e.id, status="open").first()
    if not a:
        a = Alert(elderly_id=e.id, level="Critical", stage=1,
                  reasons=i18n.reasons_to_json([{"key": "reason.sos", "params": {}}])); db.add(a); db.flush()
    a.level = "Critical"
    if a.stage < 3: a.stage = 3; db.commit(); notify(db, a)
    db.commit(); return {"ok": True}
@app.post("/elder/done/{iid}")
def elder_done(iid: int, e=Depends(elder_auth), db=Depends(get_db)):
    i = db.get(CarePlanItem, iid)
    if not i or i.elderly_id != e.id: raise HTTPException(404, "Item not found")
    today = now().strftime("%Y-%m-%d"); i.done_date = None if i.done_date == today else today; db.commit()
    return item_out(i)

# ---------- alerts, notifications, analytics, export ----------
@app.get("/alerts")
def alerts(db=Depends(get_db), u=Depends(current_user), lang: str = Depends(lang_of)):
    ppl = {e.id: e.name for e in my_people(db, u)}
    rows = db.query(Alert).filter(Alert.elderly_id.in_(list(ppl))).order_by(Alert.created_at.desc()).limit(50).all() if ppl else []
    return [{"id": a.id, "elderly_id": a.elderly_id, "name": ppl[a.elderly_id], "level": a.level,
             "reasons": i18n.reasons_text(a.reasons, lang),
             "status": a.status, "stage": a.stage, "stage_text": tr(f"stage.{a.stage}", lang), "resolved_by": a.resolved_by,
             "created_at": a.created_at.isoformat()} for a in rows]
@app.post("/alerts/{aid}/ack")
def ack(aid: int, db=Depends(get_db), u=Depends(current_user)):
    a = db.get(Alert, aid)
    if not a: raise HTTPException(404, "Alert not found")
    e = person(db, u, a.elderly_id); close_alerts(db, e, "caregiver"); db.commit(); return {"ok": True}
@app.get("/notifications")
def notifications(db=Depends(get_db), u=Depends(current_user), lang: str = Depends(lang_of)):
    q = db.query(Notification) if u.role == "admin" else db.query(Notification).filter_by(user_id=u.id)
    return [{"id": n.id, "text": i18n.render_notification(n.text, lang), "at": n.created_at.isoformat()}
            for n in q.order_by(Notification.id.desc()).limit(30)]

@app.get("/analytics")
def analytics(db=Depends(get_db), u=Depends(current_user)):
    ids = [e.id for e in my_people(db, u)]
    als = db.query(Alert).filter(Alert.elderly_id.in_(ids)).all() if ids else []
    evs = db.query(Event).filter(Event.elderly_id.in_(ids)).all() if ids else []
    days = {(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(6, -1, -1)}
    for a in als:
        d = a.created_at.strftime("%Y-%m-%d")
        if d in days: days[d] += 1
    by_hour = [0] * 24
    for x in evs:
        if x.kind == "fall": by_hour[x.created_at.hour] += 1
    rts = [(a.resolved_at - a.created_at).total_seconds() / 60 for a in als if a.resolved_at]
    self_res = sum(a.resolved_by == "person" for a in als)
    late = db.query(CheckIn).filter(CheckIn.elderly_id.in_(ids), CheckIn.responded_at == None, CheckIn.scheduled_at < now() - timedelta(minutes=30)).count() if ids else 0
    return {"alerts_per_day": days, "avg_response_min": round(sum(rts) / len(rts), 1) if rts else None,
            "falls": sum(x.kind == "fall" for x in evs), "checkin_failures": late, "total_alerts": len(als),
            "self_resolved": self_res, "false_alarm_rate": round(100 * self_res / len(als)) if als else None, "falls_by_hour": by_hour}

@app.get("/export/{name}")
def export(name: str, db=Depends(get_db), u=Depends(current_user)):
    ids = [e.id for e in my_people(db, u)]; buf = io.StringIO(); w = csv.writer(buf)
    def ins(col): return col.in_(ids)
    if name == "alerts":
        w.writerow(["id", "elderly_id", "level", "reasons", "status", "stage", "resolved_by", "created_at", "resolved_at"])
        for a in db.query(Alert).filter(ins(Alert.elderly_id)): w.writerow([a.id, a.elderly_id, a.level, i18n.reasons_text(a.reasons, "en"), a.status, a.stage, a.resolved_by, a.created_at, a.resolved_at])
    elif name == "risk":
        w.writerow(["elderly_id", "level", "score", "created_at"])
        for r in db.query(RiskLog).filter(ins(RiskLog.elderly_id)): w.writerow([r.elderly_id, r.level, r.score, r.created_at])
    elif name == "events":
        w.writerow(["id", "elderly_id", "kind", "value", "created_at"])
        for x in db.query(Event).filter(ins(Event.elderly_id)): w.writerow([x.id, x.elderly_id, x.kind, x.value, x.created_at])
    elif name == "checkins":
        w.writerow(["id", "elderly_id", "scheduled_at", "responded_at"])
        for c in db.query(CheckIn).filter(ins(CheckIn.elderly_id)): w.writerow([c.id, c.elderly_id, c.scheduled_at, c.responded_at])
    elif name == "careplan":
        w.writerow(["id", "elderly_id", "kind", "title", "time", "done_date"])
        for i in db.query(CarePlanItem).filter(ins(CarePlanItem.elderly_id)): w.writerow([i.id, i.elderly_id, i.kind, i.title, i.time, i.done_date])
    elif name == "people":  # no names, contacts or access codes
        w.writerow(["elderly_id", "age", "baseline_activity", "checkin_time", "caregiver_id"])
        for e in my_people(db, u): w.writerow([e.id, e.age, e.baseline_activity, e.checkin_time, e.caregiver_id])
    else: raise HTTPException(404, "Use alerts, risk, events, checkins, careplan or people")
    return Response(buf.getvalue(), media_type="text/csv")

# ---------- synthetic demo data ----------
@app.post("/simulate/seed")
def seed(db=Depends(get_db), _=Depends(admin_only), lang: str = Depends(lang_of)):
    """Synthetic demo data (not real people). The care-plan reminders are created in your language."""
    for m in (Notification, RiskLog, Alert, Event, CheckIn, CarePlanItem, Elderly): db.query(m).delete()
    cgs = [db.query(User).filter_by(username=n).first() or new_user(db, n, "care123") for n in ("sara", "omar")]
    names = ["Hoda Mahmoud", "Samir Fathy", "Nadia Ibrahim", "Abdel Rahman Ali", "Layla Hassan", "Mostafa Kamel",
             "Fatma Zaki", "Youssef Adel", "Salwa Naguib", "Ahmed Sherif", "Mona Said", "Kamal Aboud"]
    t = now(); today = t.strftime("%Y-%m-%d")
    for n in names:
        e = Elderly(name=n, age=random.randint(68, 90), caregiver_id=random.choice(cgs).id,
                    emergency_contact=tr("seed.contact", lang), access_code=new_code(db))
        db.add(e); db.flush()
        for kind, key, tm in [("medication", "seed.medication", "08:00"), ("meal", "seed.meal", "09:30"),
                              ("water", "seed.water", "11:00"), ("activity", "seed.activity", "17:00")]:
            db.add(CarePlanItem(elderly_id=e.id, kind=kind, title=tr(key, lang), time=tm))
        sc = random.choices(["ok", "late", "inactive", "fall"], [6, 2, 2, 2])[0]
        if sc == "ok":
            for it in db.query(CarePlanItem).filter_by(elderly_id=e.id): it.done_date = today
        for d in range(1, 8):  # a week of normal check-ins (builds the usual check-in delay)
            s = (t - timedelta(days=d)).replace(hour=9, minute=0, second=0, microsecond=0)
            db.add(CheckIn(elderly_id=e.id, scheduled_at=s, responded_at=s + timedelta(minutes=random.randint(3, 20))))
        sched = t - timedelta(minutes=60 if sc == "ok" else 180)
        db.add(CheckIn(elderly_id=e.id, scheduled_at=sched, responded_at=sched + timedelta(minutes=8) if sc == "ok" else None))
        for i in range(8):  # normal history (builds the personal baseline)
            db.add(Event(elderly_id=e.id, kind="activity", value=random.uniform(40, 60), created_at=t - timedelta(hours=random.randint(5, 70))))
        for i in range(6):
            v = random.uniform(40, 60) if sc in ("ok", "late") else random.uniform(5, 20)
            db.add(Event(elderly_id=e.id, kind="activity", value=v, created_at=t - timedelta(minutes=25 * i + 5)))
        if sc == "fall": db.add(Event(elderly_id=e.id, kind="fall", value=0.9, created_at=t - timedelta(minutes=10)))
        if random.random() < .5:  # older falls (for the "falls by hour" chart)
            hr = random.choice([2, 3, 4, 5, 6, 21, 22, 23, 9, 14])
            db.add(Event(elderly_id=e.id, kind="fall", value=0.9, created_at=(t - timedelta(days=random.randint(2, 6))).replace(hour=hr)))
        if random.random() < .6:  # past alerts for the analytics page
            c = t - timedelta(days=random.randint(1, 6), hours=random.randint(0, 5))
            db.add(Alert(elderly_id=e.id, level="High", reasons=i18n.reasons_to_json([{"key": "reason.fall_detected", "params": {}}]),
                         status="resolved", stage=3, created_at=c,
                         resolved_by=random.choice(["person", "person", "caregiver"]), resolved_at=c + timedelta(minutes=random.randint(2, 15))))
    db.commit()
    for e in db.query(Elderly).all(): evaluate(db, e)
    tick(db, True)
    return {"seeded": len(names), "caregivers": ["sara / care123", "omar / care123"]}
