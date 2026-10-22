"""English + العربية message tables.

Nothing rendered is stored in the database: alerts and notifications keep a message
*key* plus its parameters (JSON), so any message can be shown in either language at
read time. Clients ask for a language with the `Accept-Language` header, which the
frontend sets from its Settings screen.

Add a language: put a table in STRINGS and add its code to SUPPORTED.
"""
import json, os

SUPPORTED = ("en", "ar")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en") if os.getenv("DEFAULT_LANG") in SUPPORTED else "en"
LANG_NAMES = {"en": "English", "ar": "العربية"}

EN = {
    # ---------- risk reasons (keys match backend/app/risk.py) ----------
    "reason.checkin_none_2h": "No check-in for over 2 hours",
    "reason.checkin_later_than_usual": "Check-in is later than usual",
    "reason.checkin_late": "Check-in is late",
    "reason.checkin_late_today": "Check-in came later than usual today",
    "reason.activity_below_baseline": "Activity {pct}% below personal baseline",
    "reason.missed_reminders": "{n} care-plan reminders missed today",
    "reason.fall_detected": "Fall detected",
    "reason.fall_answered": "The person answered after the fall",
    "reason.fall_no_response": "No response after fall",
    "reason.fall_waiting": "Waiting for the person to answer (false-alarm check)",
    "reason.sos": "The person pressed the help button",
    # ---------- what to do next / escalation stages ----------
    "next.medium": "Ask the person: 'Are you okay?'",
    "next.high": "Notify the caregiver",
    "next.critical": "Escalate to the emergency contact",
    "stage.0": "",
    "stage.1": "Asked the person: 'Are you okay?'",
    "stage.2": "Reminder sent to the person",
    "stage.3": "Caregiver notified",
    "stage.4": "Emergency contact notified",
    # ---------- risk levels (also used as CSS data-level in English) ----------
    "level.Normal": "Normal", "level.Low": "Low", "level.Medium": "Medium",
    "level.High": "High", "level.Critical": "Critical",
    # ---------- main factors of the learned risk model ----------
    "factor.unanswered_checkin_hours": "Check-in not answered",
    "factor.late_checkin_hours": "Check-in later than usual",
    "factor.activity_drop": "Activity below personal baseline",
    "factor.activity_missing": "No recent activity data",
    "factor.night": "Night time",
    "factor.activity_drop_daytime": "Low activity during the day",
    "factor.fall_conf": "Fall detected",
    "factor.fall_waiting": "Fall detected, waiting for the person",
    "factor.fall_unanswered_verified": "No answer after a fall",
    "factor.fall_answered": "Fall, but the person answered",
    "factor.sos": "Help button pressed",
    "factor.missed_reminders": "Care-plan reminders missed",
    "factor.age": "Age",
    "factor.drop_x_unanswered": "Low activity and no check-in together",
    # ---------- notifications sent to caregivers ----------
    "notif.risk": "{name}: {level} risk. {reasons}",
    "notif.emergency": "EMERGENCY: {name} has not responded. Contact: {contact}. {reasons}",
    "notif.subject": "ElderLife alert: {name}",
    "value.not_set": "not set",
    # ---------- synthetic demo data created by /simulate/seed ----------
    "seed.medication": "Morning medication (as prescribed)",
    "seed.meal": "Breakfast",
    "seed.water": "Glass of water",
    "seed.activity": "Short walk",
    "seed.contact": "Family contact (demo)",
    # ---------- API errors (translated by the middleware, see main.py) ----------
    "err.login_required": "Please log in",
    "err.admins_only": "Admins only",
    "err.wrong_code": "Wrong code",
    "err.person_not_found": "Person not found",
    "err.bad_credentials": "Wrong username or password",
    "err.password_short": "Password must be at least 6 characters",
    "err.username_taken": "Username already exists",
    "err.caregiver_not_found": "Caregiver not found",
    "err.bad_kind": "kind must be activity, fall, ok or sos",
    "err.invalid_kind": "Invalid kind",
    "err.item_not_found": "Item not found",
    "err.alert_not_found": "Alert not found",
    "err.unsupported_lang": "Unsupported language",
}

AR = {
    # ---------- أسباب مستوى الخطر ----------
    "reason.checkin_none_2h": "لا يوجد تأكيد يومي منذ أكثر من ساعتين",
    "reason.checkin_later_than_usual": "تأكيد اليوم متأخر عن المعتاد",
    "reason.checkin_late": "تأكيد اليوم متأخر",
    "reason.checkin_late_today": "جاء تأكيد اليوم متأخرًا عن المعتاد",
    "reason.activity_below_baseline": "النشاط أقل من المعتاد الشخصي بنسبة {pct}%",
    "reason.missed_reminders": "{n} تذكيرًا من خطة الرعاية لم يُنفَّذ اليوم",
    "reason.fall_detected": "تم رصد سقطة",
    "reason.fall_answered": "أجاب الشخص بعد السقطة",
    "reason.fall_no_response": "لا استجابة بعد السقطة",
    "reason.fall_waiting": "بانتظار إجابة الشخص (للتأكد من عدم إنذار خاطئ)",
    "reason.sos": "ضغط الشخص زر الاستغاثة",
    # ---------- الخطوة التالية وخطوات التصعيد ----------
    "next.medium": "اسأل الشخص: هل أنت بخير؟",
    "next.high": "أبلغ مقدم الرعاية",
    "next.critical": "صعّد الأمر إلى جهة الاتصال الطارئ",
    "stage.0": "",
    "stage.1": "تم سؤال الشخص: هل أنت بخير؟",
    "stage.2": "تم إرسال تذكير إلى الشخص",
    "stage.3": "تم إبلاغ مقدم الرعاية",
    "stage.4": "تم إبلاغ جهة الاتصال الطارئ",
    # ---------- مستويات الخطر ----------
    "level.Normal": "طبيعي", "level.Low": "منخفض", "level.Medium": "متوسط",
    "level.High": "مرتفع", "level.Critical": "حرج",
    # ---------- أهم عوامل نموذج الخطر ----------
    "factor.unanswered_checkin_hours": "لم يُجب على تأكيد اليوم",
    "factor.late_checkin_hours": "تأكيد اليوم متأخر عن المعتاد",
    "factor.activity_drop": "نشاط أقل من المعتاد الشخصي",
    "factor.activity_missing": "لا توجد بيانات نشاط حديثة",
    "factor.night": "وقت متأخر من الليل",
    "factor.activity_drop_daytime": "نشاط منخفض أثناء النهار",
    "factor.fall_conf": "تم رصد سقطة",
    "factor.fall_waiting": "تم رصد سقطة، بانتظار الشخص",
    "factor.fall_unanswered_verified": "لا إجابة بعد السقطة",
    "factor.fall_answered": "سقطة لكن الشخص أجاب",
    "factor.sos": "تم ضغط زر الاستغاثة",
    "factor.missed_reminders": "تذكيرات خطة الرعاية لم تُنفَّذ",
    "factor.age": "العمر",
    "factor.drop_x_unanswered": "نشاط منخفض مع عدم وجود تأكيد معًا",
    # ---------- الإشعارات المرسلة لمقدمي الرعاية ----------
    "notif.risk": "{name}: مستوى الخطر {level}. {reasons}",
    "notif.emergency": "طوارئ: {name} لم يستجب. جهة الاتصال: {contact}. {reasons}",
    "notif.subject": "تنبيه ElderLife: {name}",
    "value.not_set": "غير محدد",
    # ---------- بيانات العرض التجريبية ----------
    "seed.medication": "دواء الصباح (حسب الوصفة)",
    "seed.meal": "الإفطار",
    "seed.water": "كأس ماء",
    "seed.activity": "مشية قصيرة",
    "seed.contact": "جهة اتصال عائلية (تجريبي)",
    # ---------- رسائل الواجهة البرمجية ----------
    "err.login_required": "يرجى تسجيل الدخول",
    "err.admins_only": "للمسؤولين فقط",
    "err.wrong_code": "الرمز غير صحيح",
    "err.person_not_found": "لم يتم العثور على الشخص",
    "err.bad_credentials": "اسم المستخدم أو كلمة المرور غير صحيحة",
    "err.password_short": "يجب ألا تقل كلمة المرور عن 6 أحرف",
    "err.username_taken": "اسم المستخدم موجود بالفعل",
    "err.caregiver_not_found": "لم يتم العثور على مقدم الرعاية",
    "err.bad_kind": "يجب أن يكون نوع الحدث activity أو fall أو ok أو sos",
    "err.invalid_kind": "نوع غير صالح",
    "err.item_not_found": "لم يتم العثور على العنصر",
    "err.alert_not_found": "لم يتم العثور على التنبيه",
    "err.unsupported_lang": "لغة غير مدعومة",
}

STRINGS = {"en": EN, "ar": AR}
ERROR_BY_TEXT = {EN[k]: k for k in EN if k.startswith("err.")}   # used by the error middleware


def translate_error(text, lang="en"):
    """Turn a known English HTTPException detail into the reader's language."""
    key = ERROR_BY_TEXT.get(text)
    return tr(key, lang) if key else text


def negotiate(accept_language):
    """Accept-Language header -> one of SUPPORTED, else the default language."""
    for part in (accept_language or "").split(","):
        base = part.split(";")[0].strip().lower().replace("_", "-").split("-")[0]
        if base in SUPPORTED:
            return base
    return DEFAULT_LANG


def _fill(template, params):
    for k, v in (params or {}).items():
        template = template.replace("{%s}" % k, str(v))
    return template


def tr(key, lang="en", **params):
    table = STRINGS.get(lang, EN)
    return _fill(table.get(key) or EN.get(key) or key, params)


def en_text(key, **params):
    return tr(key, "en", **params)


def reasons_to_json(codes):
    return json.dumps(codes, ensure_ascii=False)


def load_reasons(raw):
    """Alert.reasons is a JSON list of {"key", "params"}; older rows are plain English."""
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except Exception:
        return None
    if isinstance(data, list) and all(isinstance(c, dict) and "key" in c for c in data):
        return data
    return None


def reasons_text(raw, lang="en"):
    codes = load_reasons(raw)
    if codes is None:
        return raw or ""
    return "; ".join(tr(c["key"], lang, **(c.get("params") or {})) for c in codes)


def reasons_list(codes, lang="en"):
    return [tr(c["key"], lang, **(c.get("params") or {})) for c in (codes or [])]


def factor_texts(keys, lang="en"):
    return [tr("factor." + k, lang) for k in (keys or [])]


def render_notification(raw, lang="en"):
    """Notification.text is a JSON {key, params}; older rows are plain English."""
    if not isinstance(raw, str):
        return raw
    try:
        data = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(data, dict) or "key" not in data:
        return raw
    p = dict(data.get("params") or {})
    codes = p.pop("reason_codes", None)
    if codes is not None:
        p["reasons"] = reasons_text(codes, lang)
    if p.get("level"):
        p["level"] = tr("level." + str(p["level"]), lang)
    if not p.get("contact"):
        p["contact"] = tr("value.not_set", lang)
    return tr(data["key"], lang, **p)
