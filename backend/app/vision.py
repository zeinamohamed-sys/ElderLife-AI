"""Pose-based activity and fall heuristics (no images are ever stored, only keypoints).
This is a rule-based placeholder with the same contract a trained model would use:
classify(keypoints, prev_keypoints, dt_s) -> (activity, confidence).
Keypoints are normalised image coordinates [x, y], y grows downward."""
import math, os
from .mlmodels import Logistic, load_json

POINTS = ["nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip",
          "left_knee", "right_knee", "left_ankle", "right_ankle"]
ACTIVITY_LEVEL = {"lying": 5, "falling": 5, "sitting": 15, "bending": 30, "standing": 35, "walking": 60}

def _mid(k, a, b): return ((k[a][0] + k[b][0]) / 2, (k[a][1] + k[b][1]) / 2)

def features(k):
    sh, hip = _mid(k, "left_shoulder", "right_shoulder"), _mid(k, "left_hip", "right_hip")
    knee = _mid(k, "left_knee", "right_knee")
    torso = math.hypot(hip[0] - sh[0], hip[1] - sh[1]) or 1e-6
    angle = math.degrees(math.atan2(abs(hip[0] - sh[0]), abs(hip[1] - sh[1])))  # 0 upright, 90 horizontal
    xs, ys = [k[p][0] for p in POINTS], [k[p][1] for p in POINTS]
    return {"angle": angle, "aspect": (max(xs) - min(xs)) / ((max(ys) - min(ys)) or 1e-6),
            "hip": hip, "torso": torso, "hip_knee": abs(hip[1] - knee[1]) / torso}

def classify(k, prev=None, dt=None):
    f, p = features(k), (features(prev) if prev else None)
    if p and dt and dt > 0:
        drop = (f["hip"][1] - p["hip"][1]) / f["torso"] / dt   # torso lengths per second, downward
        if drop > 0.8 and f["angle"] > 40:
            return "falling", round(min(1.0, 0.6 + 0.4 * min(1.0, drop / 1.6)), 2)
        if p["angle"] < 30 and f["angle"] > 60 and dt <= 2:
            return "falling", 0.8
    if f["angle"] > 60 or f["aspect"] > 1.2: return "lying", 0.8
    if f["angle"] > 30: return "bending", 0.7
    if f["hip_knee"] < 0.45: return "sitting", 0.8
    if p and dt and dt > 0:
        moved = math.hypot(f["hip"][0] - p["hip"][0], f["hip"][1] - p["hip"][1]) / f["torso"] / dt
        if moved > 0.3: return "walking", 0.8
    return "standing", 0.8

def _pose(nose, sh, hip, knee, ank, s=0.04):
    k = {"nose": list(nose)}
    for name, p in (("shoulder", sh), ("hip", hip), ("knee", knee), ("ankle", ank)):
        k[f"left_{name}"], k[f"right_{name}"] = [p[0] - s, p[1]], [p[0] + s, p[1]]
    return k

def sample_pose(kind, x=0.5):
    """Synthetic poses for tests and the simulator."""
    return {
        "standing": lambda: _pose((x, .22), (x, .30), (x, .55), (x, .75), (x, .95)),
        "sitting": lambda: _pose((x, .37), (x, .45), (x, .70), (x + .15, .72), (x + .15, .95)),
        "bending": lambda: _pose((x + .17, .38), (x + .12, .45), (x, .60), (x, .78), (x, .95)),
        "falling": lambda: _pose((x - .2, .55), (x - .12, .60), (x, .62), (x + .1, .8), (x + .2, .95)),
        "lying": lambda: _pose((x - .32, .84), (x - .25, .85), (x, .85), (x + .2, .86), (x + .4, .87)),
    }[kind]()


# ---------------- learned activity / fall model ----------------
POSE_CLASSES = ["standing", "walking", "sitting", "bending", "lying", "falling"]
POSE_FEATURES = ["angle", "aspect", "hip_knee", "drop", "moved", "has_prev", "angle_change", "angle_bump", "thigh_low"]

def pose_vector(k, prev=None, dt=None):
    f = features(k); drop = moved = change = has = 0.0
    if prev and dt and dt > 0:
        p = features(prev); has = 1.0
        drop = max(-3.0, min(5.0, (f["hip"][1] - p["hip"][1]) / f["torso"] / dt))
        moved = min(3.0, math.hypot(f["hip"][0] - p["hip"][0], f["hip"][1] - p["hip"][1]) / f["torso"] / dt)
        change = (f["angle"] - p["angle"]) / 90.0
    a = f["angle"]
    return [a / 90, min(f["aspect"], 4) / 2, min(f["hip_knee"], 2), drop / 2, moved, has, change,
            max(0.0, 1 - abs(a - 45) / 25), max(0.0, 0.6 - f["hip_knee"])]

_POSE = load_json("pose_model.json")
POSE_MODELS = {c: Logistic.from_dict(d) for c, d in _POSE["models"].items()} if _POSE else None

def classify_ml(k, prev=None, dt=None):
    x = pose_vector(k, prev, dt); probs = {c: m.predict(x) for c, m in POSE_MODELS.items()}
    best = max(probs, key=probs.get); return best, round(probs[best] / (sum(probs.values()) or 1.0), 2)

def classify_auto(k, prev=None, dt=None):
    """Uses the trained model when available (ML_MODE != off), otherwise the rule-based heuristic."""
    if POSE_MODELS and os.getenv("ML_MODE", "auto") != "off":
        return (*classify_ml(k, prev, dt), "ml")
    return (*classify(k, prev, dt), "rules")
