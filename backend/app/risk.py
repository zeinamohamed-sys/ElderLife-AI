"""Risk engine contract (swap the body for your ML model, keep the signature).

Input keys:
  checkin_delay_min, checkin_responded, checkin_usual_min (None if unknown),
  activity_ratio (vs personal baseline, None if no data),
  fall, fall_answered, fall_age_s, verify_s, sos, missed_reminders
Output: {"level", "score", "reasons": [...English...], "reason_codes": [{"key", "params"}, ...]}

`reasons` stays in English for logs, exports and the tests; `reason_codes` is what the API
translates for the reader (see app/i18n.py).
"""
import os
from .i18n import en_text
from .mlmodels import Logistic, load_json

LEVELS = ["Normal", "Low", "Medium", "High", "Critical"]
NEXT_STEP = {
    "Medium": "Ask the person: 'Are you okay?'",
    "High": "Notify the caregiver",
    "Critical": "Escalate to the emergency contact",
}

def _reason(codes: list, key: str, **params) -> str:
    """Record the translatable reason and return its English text."""
    codes.append({"key": key, "params": params})
    return en_text(key, **params)

def assess_rules(s: dict) -> dict:
    score, reasons, codes = 0.0, [], []
    d, usual = s["checkin_delay_min"], s.get("checkin_usual_min")
    late_after = usual + 20 if usual is not None else 30   # personalised "late" threshold
    if not s.get("checkin_responded", False):
        if d >= 120:
            score += 0.3; reasons.append(_reason(codes, "reason.checkin_none_2h"))
        elif d >= late_after:
            score += 0.15
            reasons.append(_reason(codes, "reason.checkin_later_than_usual" if usual is not None else "reason.checkin_late"))
    elif d >= late_after:
        score += 0.05; reasons.append(_reason(codes, "reason.checkin_late_today"))
    r = s["activity_ratio"]
    if r is not None and r < 0.5:
        score += 0.25; reasons.append(_reason(codes, "reason.activity_below_baseline", pct=round((1 - r) * 100)))
    m = s.get("missed_reminders", 0)
    if m >= 2:
        score += 0.1; reasons.append(_reason(codes, "reason.missed_reminders", n=m))
    if s["fall"]:
        reasons.append(_reason(codes, "reason.fall_detected"))
        if s["fall_answered"]:
            score += 0.15; reasons.append(_reason(codes, "reason.fall_answered"))
        else:
            score += 0.3
            if s.get("fall_age_s", 9999) >= s.get("verify_s", 60):
                score += 0.3; reasons.append(_reason(codes, "reason.fall_no_response"))
            else:
                reasons.append(_reason(codes, "reason.fall_waiting"))
    if s.get("sos"):
        score += 0.8; reasons.append(_reason(codes, "reason.sos"))
    score = min(score, 1.0)
    level = LEVELS[0 if score < .1 else 1 if score < .25 else 2 if score < .5 else 3 if score < .75 else 4]
    return {"level": level, "score": round(score, 2), "reasons": reasons, "reason_codes": codes}


# ---------------- learned risk model (hybrid: model + safety rules) ----------------
FEATURES = ["unanswered_checkin_hours", "late_checkin_hours", "activity_drop", "activity_missing", "night",
            "activity_drop_daytime", "fall_conf", "fall_waiting", "fall_unanswered_verified", "fall_answered",
            "sos", "missed_reminders", "age", "drop_x_unanswered"]
FACTOR_TEXT = {
    "unanswered_checkin_hours": "Check-in not answered", "late_checkin_hours": "Check-in later than usual",
    "activity_drop": "Activity below personal baseline", "activity_missing": "No recent activity data",
    "night": "Night time", "activity_drop_daytime": "Low activity during the day", "fall_conf": "Fall detected",
    "fall_waiting": "Fall detected, waiting for the person", "fall_unanswered_verified": "No answer after a fall",
    "fall_answered": "Fall, but the person answered", "sos": "Help button pressed",
    "missed_reminders": "Care-plan reminders missed", "age": "Age", "drop_x_unanswered": "Low activity and no check-in together",
}

def features_from_signals(s: dict) -> list:
    """Same function is used for training and for serving, so the two can never drift apart."""
    d, responded = s["checkin_delay_min"], s.get("checkin_responded", False)
    ref = s["checkin_usual_min"] if s.get("checkin_usual_min") is not None else 10
    un_h = 0.0 if responded else min(d, 360) / 60
    late_h = min(max(0, d - (ref + 20)), 180) / 60 if responded else 0.0
    r = s["activity_ratio"]; drop = 0.0 if r is None else min(max(0.0, 1 - r), 1.0)
    hour = s.get("hour", 12); night = 1.0 if (hour < 6 or hour >= 22) else 0.0
    fall, answered = bool(s["fall"]), bool(s["fall_answered"])
    verified = fall and not answered and s.get("fall_age_s", 0) >= s.get("verify_s", 60)
    waiting = fall and not answered and not verified
    return [un_h, late_h, drop, 1.0 if r is None else 0.0, night, drop * (1 - night),
            s.get("fall_conf", 1.0) if fall else 0.0, float(waiting), float(verified), float(fall and answered),
            float(bool(s.get("sos"))), min(s.get("missed_reminders", 0), 4) / 4, (s.get("age", 78) - 78) / 10,
            drop * min(un_h, 4)]

def ml_level_index(p: float, th: dict, s: dict):
    """Model probability -> level, but known emergencies can never be hidden by the model (safety floor)."""
    idx = sum(p >= th[k] for k in ("low", "medium", "high", "critical"))
    floor = 4 if s.get("sos") else 3 if (s["fall"] and not s["fall_answered"] and s.get("fall_age_s", 0) >= s.get("verify_s", 60)) else 0
    return max(idx, floor), floor

_RISK = load_json("risk_model.json")
MODEL = Logistic.from_dict(_RISK["model"]) if _RISK else None
THRESHOLDS = _RISK["thresholds"] if _RISK else None

def ml_enabled() -> bool:
    return MODEL is not None and os.getenv("ML_MODE", "auto") != "off"

def assess(s: dict) -> dict:
    rules = assess_rules(s)
    if not ml_enabled(): return {**rules, "model": None}
    x = features_from_signals(s); p = MODEL.predict(x)
    idx, floor = ml_level_index(p, THRESHOLDS, s)
    top_keys = [k for k, v in sorted(MODEL.contributions(x).items(), key=lambda kv: -kv[1]) if v > 0.3][:3]
    score = max(p, 0.7 if floor == 4 else 0.4 if floor == 3 else 0.0)
    return {"level": LEVELS[idx], "score": round(score, 2), "reasons": rules["reasons"], "reason_codes": rules["reason_codes"],
            "model": {"mode": "hybrid", "probability": round(p, 3), "top_factors": [FACTOR_TEXT[k] for k in top_keys],
                      "top_factor_keys": top_keys, "safety_floor": LEVELS[floor] if floor else None}}
