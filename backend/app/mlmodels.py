"""Tiny dependency-free logistic regression (train + predict). Used for the risk and pose models.
Models are stored as JSON in app/models/, so the backend needs no ML library at run time.
Explanations come for free: contribution of a feature = weight * standardised value (log-odds)."""
import json, math, os

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

def sigmoid(z):
    if z >= 0: return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z); return e / (1.0 + e)

class Logistic:
    def __init__(self, names, w=None, b=0.0, mean=None, std=None):
        n = len(names); self.names = list(names)
        self.w, self.b = w or [0.0] * n, b
        self.mean, self.std = mean or [0.0] * n, std or [1.0] * n
    def scaled(self, x): return [(v - m) / s for v, m, s in zip(x, self.mean, self.std)]
    def logit(self, x): return self.b + sum(w * v for w, v in zip(self.w, self.scaled(x)))
    def predict(self, x): return sigmoid(self.logit(x))
    def contributions(self, x): return dict(zip(self.names, (w * v for w, v in zip(self.w, self.scaled(x)))))

    def fit(self, X, y, epochs=250, lr=1.0, l2=1e-3):
        n, d = len(X), len(self.names)
        self.mean = [sum(r[j] for r in X) / n for j in range(d)]
        self.std = [(sum((r[j] - self.mean[j]) ** 2 for r in X) / n) ** 0.5 or 1.0 for j in range(d)]
        Z = [[(r[j] - self.mean[j]) / self.std[j] for j in range(d)] for r in X]
        p0 = min(max(sum(y) / n, 1e-4), 1 - 1e-4); self.b = math.log(p0 / (1 - p0)); self.w = [0.0] * d
        for ep in range(epochs):
            gw, gb = [0.0] * d, 0.0
            for z, t in zip(Z, y):
                e = sigmoid(self.b + sum(a * c for a, c in zip(self.w, z))) - t
                gb += e
                for j in range(d): gw[j] += e * z[j]
            step = lr / (1 + ep / 80)
            self.b -= step * gb / n
            for j in range(d): self.w[j] -= step * (gw[j] / n + l2 * self.w[j])
        return self

    def to_dict(self): return {"names": self.names, "w": self.w, "b": self.b, "mean": self.mean, "std": self.std}
    @staticmethod
    def from_dict(d): return Logistic(d["names"], d["w"], d["b"], d["mean"], d["std"])

def load_json(name):
    try:
        with open(os.path.join(MODEL_DIR, name), encoding="utf-8") as f: return json.load(f)
    except Exception: return None

def save_json(name, obj):
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(os.path.join(MODEL_DIR, name), "w", encoding="utf-8") as f: json.dump(obj, f, indent=1)
