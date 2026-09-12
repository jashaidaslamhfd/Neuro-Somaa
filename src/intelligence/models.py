#!/usr/bin/env python3
"""Pure-numpy models for the intelligence layer (CPU/GitHub-runner safe).

- RidgeRegression: closed-form (XᵀX + λI)⁻¹Xᵀy with standardization + k-fold CV.
- TinyMLP: 1-hidden-layer tanh network, full-batch gradient descent.
  "DL" honestly scaled to n≈50 rows: it will only report results when data
  suffices, and always ships cross-validated metrics, never vanity fits.

Everything reports its own uncertainty; callers decide what to trust.
"""

from __future__ import annotations

import math


def _to_matrix(rows: list[dict], names: list[str]):
    import numpy as np

    X = np.array([[r.get(n, 0.0) for n in names] for r in rows], dtype=float)
    return X


class RidgeRegression:
    def __init__(self, lam: float = 10.0):
        self.lam = lam
        self.coef_ = None
        self.names_: list[str] = []
        self.x_mean = self.x_std = self.y_mean = self.y_std = None

    def fit(self, rows: list[dict], y: list[float], names: list[str]):
        import numpy as np

        X = _to_matrix(rows, names)
        Y = np.array(y, dtype=float)
        self.x_mean, self.x_std = X.mean(axis=0), X.std(axis=0)
        self.x_std = np.where(self.x_std < 1e-9, 1.0, self.x_std)
        self.y_mean, self.y_std = float(Y.mean()), float(Y.std() or 1.0)
        Xs = (X - self.x_mean) / self.x_std
        Ys = (Y - self.y_mean) / self.y_std
        n_feat = Xs.shape[1]
        A = Xs.T @ Xs + self.lam * np.eye(n_feat)
        b = Xs.T @ Ys
        self.coef_ = np.linalg.solve(A, b)
        self.names_ = names
        return self

    def predict_log(self, row: dict) -> float:
        import numpy as np

        x = np.array([row.get(n, 0.0) for n in self.names_], dtype=float)
        xs = (x - self.x_mean) / self.x_std
        return float(xs @ self.coef_ * self.y_std + self.y_mean)

    def predict_views(self, row: dict) -> float:
        return max(0.0, math.expm1(self.predict_log(row)))

    def top_features(self, k: int = 8) -> list[dict]:
        import numpy as np

        order = np.argsort(-np.abs(self.coef_))[:k]
        return [
            {
                "feature": self.names_[i],
                "coef": round(float(self.coef_[i]), 4),
                "direction": "+" if self.coef_[i] >= 0 else "-",
            }
            for i in order
        ]


def kfold_r2(rows: list[dict], y: list[float], names: list[str], k: int = 5, lam: float = 10.0) -> dict:
    """K-fold cross-validated R² + MAE(in views) for the ridge model."""
    import numpy as np

    n = len(rows)
    if n < max(12, k * 3):
        return {"reliable": False, "reason": f"insufficient data (n={n})", "n": n}
    k = min(k, n // 3)
    idx = np.arange(n)
    rng = np.random.default_rng(42)
    rng.shuffle(idx)
    folds = np.array_split(idx, k)
    r2s, maes = [], []
    for i in range(k):
        test_i = folds[i]
        train_i = np.concatenate([folds[j] for j in range(k) if j != i])
        tr_rows = [rows[j] for j in train_i]
        tr_y = [y[j] for j in train_i]
        model = RidgeRegression(lam=lam).fit(tr_rows, tr_y, names)
        y_true = np.array([y[j] for j in test_i])
        y_pred = np.array([model.predict_log(rows[j]) for j in test_i])
        ss_res = float(np.sum((y_true - y_pred) ** 2))
        ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
        r2s.append(1 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0)
        maes.append(
            float(np.mean([abs(math.expm1(a) - math.expm1(b)) for a, b in zip(y_true, y_pred, strict=False)]))
        )
    return {
        "reliable": bool(np.mean(r2s) > 0.10),
        "cv_r2_mean": round(float(np.mean(r2s)), 4),
        "cv_r2_std": round(float(np.std(r2s)), 4),
        "cv_mae_views": round(float(np.mean(maes)), 1),
        "n": n,
        "folds": k,
        "note": "r²<=0.10 = noise-level model; treat coefficients as hints only.",
    }


class TinyMLP:
    """1-hidden-layer tanh MLP, pure numpy, full-batch GD.

    Deliberately tiny: with n≈50 rows, a big network would just memorize.
    """

    def __init__(self, hidden: int = 12, epochs: int = 600, lr: float = 0.03, seed: int = 7):
        self.hidden, self.epochs, self.lr, self.seed = hidden, epochs, lr, seed

    def fit(self, rows: list[dict], y: list[float], names: list[str]):
        import numpy as np

        X = _to_matrix(rows, names)
        Y = np.array(y, dtype=float).reshape(-1, 1)
        self.names_ = names
        self.x_mean, self.x_std = X.mean(axis=0), X.std(axis=0)
        self.x_std = np.where(self.x_std < 1e-9, 1.0, self.x_std)
        self.y_mean, self.y_std = float(Y.mean()), float(Y.std() or 1.0)
        Xs = (X - self.x_mean) / self.x_std
        Ys = (Y - self.y_mean) / self.y_std

        rng = np.random.default_rng(self.seed)
        n_feat = Xs.shape[1]
        self.W1 = rng.normal(0, 1 / math.sqrt(n_feat), (n_feat, self.hidden))
        self.b1 = np.zeros((1, self.hidden))
        self.W2 = rng.normal(0, 1 / math.sqrt(self.hidden), (self.hidden, 1))
        self.b2 = np.zeros((1, 1))

        n = Xs.shape[0]
        for _ in range(self.epochs):
            H = np.tanh(Xs @ self.W1 + self.b1)
            out = H @ self.W2 + self.b2
            err = (out - Ys) / n
            dW2 = H.T @ err
            db2 = err.sum(axis=0, keepdims=True)
            dH = (err @ self.W2.T) * (1 - H**2)
            dW1 = Xs.T @ dH
            db1 = dH.sum(axis=0, keepdims=True)
            self.W2 -= self.lr * dW2
            self.b2 -= self.lr * db2
            self.W1 -= self.lr * dW1
            self.b1 -= self.lr * db1
        return self

    def predict_views(self, row: dict) -> float:
        import numpy as np

        x = np.array([[row.get(n, 0.0) for n in self.names_]], dtype=float)
        xs = (x - self.x_mean) / self.x_std
        out = np.tanh(xs @ self.W1 + self.b1) @ self.W2 + self.b2
        return max(0.0, math.expm1(float(out[0, 0]) * self.y_std + self.y_mean))


def compare_models(rows: list[dict], y: list[float], names: list[str]) -> dict:
    """Train ridge + MLP, report honest comparison. MLP requires n>=40."""
    if not rows:
        return {
            "ridge": {"reliable": False, "reason": "no real-analytics rows yet", "n": 0},
            "mlp": {"reliable": False, "reason": "no real-analytics rows yet"},
        }
    out = {"ridge": kfold_r2(rows, y, names)}
    ridge = RidgeRegression().fit(rows, y, names)
    out["ridge"]["top_features"] = ridge.top_features()
    out["mlp"] = {"reliable": False, "reason": "n<40 — deep model withheld to avoid memorization"}
    if len(rows) >= 40:
        try:
            mlp = TinyMLP().fit(rows, y, names)
            preds = [mlp.predict_views(r) for r in rows]
            import math as _m

            import numpy as np

            true_v = [_m.expm1(t) for t in y]
            mae = float(np.mean([abs(a - b) for a, b in zip(true_v, preds, strict=False)]))
            out["mlp"] = {
                "reliable": False,  # in-sample only; used as a signal, never a gate
                "note": f"in-sample fit on n={len(rows)}; advisory only",
                "in_sample_mae_views": round(mae, 1),
                "hidden_units": mlp.hidden,
                "epochs": mlp.epochs,
            }
        except Exception as exc:
            out["mlp"] = {"reliable": False, "reason": str(exc)[:120]}
    return out
