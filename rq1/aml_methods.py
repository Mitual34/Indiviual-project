"""Tabular methods surveyed in Jensen & Iosifidis (2023), "Fighting Money Laundering with
Statistics and Machine Learning" (IEEE Access 11; arXiv:2201.04207), implemented as library code.

Equation numbers refer to the paper. Everything is numpy-first so the maths is visible; sklearn is used only
where the paper itself cites an off-the-shelf method (isolation forest, one-class SVM, Gaussian mixture).

NOT implemented (not tabular): graph convolution (Eq 14), RNN/LSTM/attention (Eq 15-19), GAN/VAE,
Deng et al.'s sequential D-optimal active learning. The paper under-specifies how Camino et al. combine their three
detectors; `outlier_ensemble` uses rank averaging and says so.
"""
from __future__ import annotations
import numpy as np
from scipy.stats import rankdata, chi2
from scipy.special import expit
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.mixture import GaussianMixture
from sklearn.metrics import cohen_kappa_score, roc_curve


# ---------------------------------------------------------------- 3.1 clustering
def kmeans(X, K, n_iter=100, seed=0, tol=1e-9):
    """Lloyd's algorithm for Eq 7: argmin sum_k sum_{c in rho_k} ||x_c - mu_k||^2.
    Returns (centroids, labels, objective). Alexandre & Balsa use K=7."""
    X = np.asarray(X, float); rng = np.random.default_rng(seed)
    mu = [X[rng.integers(len(X))]]  # k-means++ seeding: next centre drawn with prob proportional to squared distance
    for _ in range(K - 1):
        d2 = ((X[:, None] - np.array(mu)[None]) ** 2).sum(-1).min(1)
        mu.append(X[rng.choice(len(X), p=d2 / d2.sum())])
    mu = np.array(mu); prev = np.inf
    for _ in range(n_iter):
        d = ((X[:, None, :] - mu[None]) ** 2).sum(-1); lab = d.argmin(1)
        for k in range(K):
            if (lab == k).any(): mu[k] = X[lab == k].mean(0)
        obj = float(d[np.arange(len(X)), lab].sum())
        if prev - obj < tol: break
        prev = obj
    return mu, lab, obj


def kmeans_distance(X, centroids):
    """Distance to nearest centroid; a simple outlier / risk score."""
    return np.sqrt(((np.asarray(X, float)[:, None] - centroids[None]) ** 2).sum(-1)).min(1)


def fuzzy_cmeans(X, C, m=2.0, n_iter=200, seed=0, tol=1e-6):
    """Fuzzy C-means (Rocha-Salazar et al.; Raza & Haider): soft memberships u_ck, fuzzifier m>1.
    Returns (centers, U) with U of shape (n, C), rows summing to 1."""
    X = np.asarray(X, float); rng = np.random.default_rng(seed)
    U = rng.random((len(X), C)); U /= U.sum(1, keepdims=True)
    for _ in range(n_iter):
        W = U ** m; V = (W.T @ X) / W.sum(0)[:, None]
        d = np.sqrt(((X[:, None] - V[None]) ** 2).sum(-1)) + 1e-12
        Un = 1.0 / ((d[:, :, None] / d[:, None, :]) ** (2 / (m - 1))).sum(-1)
        if np.abs(Un - U).max() < tol: U = Un; break
        U = Un
    return V, U


# ---------------------------------------------------------------- 4.1 PCA
def pca(X, q):
    """Eq 11: u_1 = argmax u'Su s.t. u'u=1, and successive orthogonal directions = top eigenvectors of covariance S.
    Returns (components (q,d), explained_variance (q,), mean). Project with (X-mean)@components.T."""
    X = np.asarray(X, float); mean = X.mean(0); S = np.cov(X - mean, rowvar=False)
    w, V = np.linalg.eigh(S); order = np.argsort(w)[::-1][:q]
    return V[:, order].T, w[order], mean


# ---------------------------------------------------------------- 3.1 autoencoder (Eq 8)
class Autoencoder:
    """Feedforward network nn(x)=phi(L)(...phi(1)(xW1+b1)...WL+bL) trained to reproduce its input (o_c = x_c).
    Paula et al. use layers 18-6-3-6-18 (the last must equal the input dimension). tanh hidden, linear output,
    full-batch Adam on squared error. Risk score rho(x)=(1/q)||nn(x)-x||^2 (reconstruction error)."""

    def __init__(self, layer_sizes=(18, 6, 3, 6, 18), lr=0.01, epochs=500, seed=0):
        self.sizes, self.lr, self.epochs, self.seed = tuple(layer_sizes), lr, epochs, seed

    def _fwd(self, X):
        acts = [X]
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = acts[-1] @ W + b
            acts.append(z if i == len(self.W) - 1 else np.tanh(z))
        return acts

    def fit(self, X):
        X = np.asarray(X, float); d = X.shape[1]
        assert self.sizes[-1] == d, f"last layer size {self.sizes[-1]} must equal input dim {d}"
        rng = np.random.default_rng(self.seed); dims = (d,) + self.sizes
        self.W = [rng.normal(0, np.sqrt(1 / dims[i]), (dims[i], dims[i + 1])) for i in range(len(self.sizes))]  # LeCun init
        self.b = [np.zeros(s) for s in self.sizes]
        mW = [np.zeros_like(w) for w in self.W]; vW = [np.zeros_like(w) for w in self.W]
        mb = [np.zeros_like(b) for b in self.b]; vb = [np.zeros_like(b) for b in self.b]
        n = len(X); self.loss_ = []
        for t in range(1, self.epochs + 1):
            acts = self._fwd(X); delta = 2 * (acts[-1] - X) / n
            self.loss_.append(float(((acts[-1] - X) ** 2).sum(1).mean()))
            for i in reversed(range(len(self.W))):
                gW = acts[i].T @ delta; gb = delta.sum(0)
                if i > 0: delta = (delta @ self.W[i].T) * (1 - acts[i] ** 2)
                for p, g, m_, v_ in ((self.W, gW, mW, vW), (self.b, gb, mb, vb)):
                    m_[i] = 0.9 * m_[i] + 0.1 * g; v_[i] = 0.999 * v_[i] + 0.001 * g ** 2
                    p[i] -= self.lr * (m_[i] / (1 - 0.9 ** t)) / (np.sqrt(v_[i] / (1 - 0.999 ** t)) + 1e-8)
        return self

    def reconstruct(self, X): return self._fwd(np.asarray(X, float))[-1]

    def score(self, X):
        X = np.asarray(X, float); return ((self.reconstruct(X) - X) ** 2).mean(1)


# ---------------------------------------------------------------- 3.2 logistic regression (Eq 9)
class LogisticRegressionGD:
    """P(y=1|x)=exp(b'x)/(1+exp(b'x)) (Eq 9), fitted by Newton/IRLS with optional L2 and per-sample weights
    (the 'weighing observations' imbalance remedy of Badal-Valero et al.). Intercept is not penalised."""

    def __init__(self, l2=1e-3, max_iter=100, tol=1e-8): self.l2, self.max_iter, self.tol = l2, max_iter, tol

    def fit(self, X, y, sample_weight=None):
        X = np.c_[np.ones(len(X)), np.asarray(X, float)]; y = np.asarray(y, float)
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, float)
        beta = np.zeros(X.shape[1]); P = np.eye(X.shape[1]) * self.l2; P[0, 0] = 0
        for _ in range(self.max_iter):
            p = expit(X @ beta); g = X.T @ (w * (p - y)) + P @ beta
            H = (X * (w * p * (1 - p))[:, None]).T @ X + P + 1e-10 * np.eye(len(beta))
            step = np.linalg.solve(H, g); beta -= step
            if np.abs(step).max() < self.tol: break
        self.intercept_, self.coef_ = beta[0], beta[1:]; return self

    def predict_proba(self, X): return expit(np.asarray(X, float) @ self.coef_ + self.intercept_)


def balanced_weights(y):
    """Weights inversely proportional to class frequency."""
    y = np.asarray(y); n = len(y); return np.where(y == 1, n / (2 * y.sum()), n / (2 * (n - y.sum())))


# ---------------------------------------------------------------- 4.1 outlier ensemble (Camino et al.)
def outlier_ensemble(X_fit, X_score, seed=0, nu=0.1, n_components=3):
    """Isolation forest + one-class SVM + Gaussian mixture, combined by averaging normalised ranks (paper does not
    specify the combination rule). Higher = more outlying. Returns (ensemble, dict of component scores)."""
    X_fit, X_score = np.asarray(X_fit, float), np.asarray(X_score, float)
    s = {"isolation_forest": -IsolationForest(random_state=seed).fit(X_fit).score_samples(X_score),
         "one_class_svm": -OneClassSVM(nu=nu, gamma="scale").fit(X_fit).score_samples(X_score),
         "gaussian_mixture": -GaussianMixture(n_components, random_state=seed).fit(X_fit).score_samples(X_score)}
    ranks = np.mean([rankdata(v) / len(v) for v in s.values()], axis=0)
    return ranks, s


# ---------------------------------------------------------------- 5.1 resampling
def random_oversample(X, y, seed=0):
    rng = np.random.default_rng(seed); X, y = np.asarray(X), np.asarray(y)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    mn, mj = (pos, neg) if len(pos) < len(neg) else (neg, pos)
    idx = np.concatenate([mj, mn, rng.choice(mn, len(mj) - len(mn), replace=True)]); return X[idx], y[idx]


def random_undersample(X, y, seed=0):
    rng = np.random.default_rng(seed); X, y = np.asarray(X), np.asarray(y)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    mn, mj = (pos, neg) if len(pos) < len(neg) else (neg, pos)
    idx = np.concatenate([mn, rng.choice(mj, len(mn), replace=False)]); return X[idx], y[idx]


def _knn(A, B, k, exclude_self=False):
    d = ((A[:, None] - B[None]) ** 2).sum(-1)
    if exclude_self: np.fill_diagonal(d, np.inf)
    return np.argsort(d, 1)[:, :k]


def smote(X, y, k=5, n_new=None, seed=0, minority=1):
    """SMOTE (Chawla et al.): synthetic = x + u (x_nn - x), u~U(0,1), x_nn one of the k nearest minority neighbours.
    Returns the augmented (X, y)."""
    rng = np.random.default_rng(seed); X, y = np.asarray(X, float), np.asarray(y)
    Xm = X[y == minority]; k = min(k, len(Xm) - 1)
    n_new = (y != minority).sum() - len(Xm) if n_new is None else n_new
    nn = _knn(Xm, Xm, k, exclude_self=True); base = rng.integers(0, len(Xm), n_new)
    nb = nn[base, rng.integers(0, k, n_new)]
    new = Xm[base] + rng.random((n_new, 1)) * (Xm[nb] - Xm[base])
    return np.vstack([X, new]), np.concatenate([y, np.full(n_new, minority)])


def borderline_smote(X, y, k=5, m=5, n_new=None, seed=0, minority=1):
    """Borderline-SMOTE1 (Han et al.): only minority points in 'danger' (>= m/2 but < m of their m nearest
    neighbours in the full data are majority) seed synthetic samples; interpolation is towards minority neighbours."""
    rng = np.random.default_rng(seed); X, y = np.asarray(X, float), np.asarray(y)
    Xm = X[y == minority]; nnall = _knn(Xm, X, m + 1)[:, 1:]  # drop self (distance 0 is first)
    maj = (y[nnall] != minority).sum(1); danger = np.where((maj >= m / 2) & (maj < m))[0]
    if len(danger) == 0: return X.copy(), y.copy()
    k = min(k, len(Xm) - 1); nnm = _knn(Xm[danger], Xm, k + 1)[:, 1:]
    n_new = (y != minority).sum() - len(Xm) if n_new is None else n_new
    b = rng.integers(0, len(danger), n_new); nb = nnm[b, rng.integers(0, k, n_new)]
    new = Xm[danger][b] + rng.random((n_new, 1)) * (Xm[nb] - Xm[danger][b])
    return np.vstack([X, new]), np.concatenate([y, np.full(n_new, minority)])


def adasyn(X, y, k=5, beta=1.0, seed=0, minority=1):
    """ADASYN (He et al.): number of synthetic samples per minority point proportional to the share of majority
    points among its k nearest neighbours (harder regions get more), then SMOTE-style interpolation."""
    rng = np.random.default_rng(seed); X, y = np.asarray(X, float), np.asarray(y)
    Xm = X[y == minority]; G = int((y != minority).sum() - len(Xm)) * beta
    nnall = _knn(Xm, X, k + 1)[:, 1:]; r = (y[nnall] != minority).mean(1)
    if r.sum() == 0: return X.copy(), y.copy()
    g = np.rint(r / r.sum() * G).astype(int); km = min(k, len(Xm) - 1); nnm = _knn(Xm, Xm, km, exclude_self=True)
    new = [Xm[i] + rng.random() * (Xm[nnm[i, rng.integers(0, km)]] - Xm[i]) for i in range(len(Xm)) for _ in range(g[i])]
    if not new: return X.copy(), y.copy()
    return np.vstack([X, np.array(new)]), np.concatenate([y, np.full(len(new), minority)])


# ---------------------------------------------------------------- 3.2 Benford's law (Badal-Valero et al.)
BENFORD = np.log10(1 + 1 / np.arange(1, 10))


def first_digits(values):
    v = np.abs(np.asarray(values, float)); v = v[v > 0]
    return np.floor(v / 10 ** np.floor(np.log10(v))).astype(int)


def benford_features(values):
    """Observed first-digit distribution vs Benford: returns dict with observed freqs, chi-square statistic and
    p-value (8 dof), and mean absolute deviation (MAD). Features for flagging manipulated statements."""
    d = first_digits(values); n = len(d)
    obs = np.array([(d == i).sum() for i in range(1, 10)]); freq = obs / n
    chi = float((((obs - n * BENFORD) ** 2) / (n * BENFORD)).sum())
    return dict(n=n, observed=freq, chi_square=chi, p_value=float(chi2.sf(chi, 8)), mad=float(np.abs(freq - BENFORD).mean()))


# ---------------------------------------------------------------- 4.2 active learning (uncertainty sampling)
def uncertainty_sampling(proba, n):
    """Indices of the n unlabeled points whose predicted P(y=1) is closest to 0.5 (Lewis & Gale-style)."""
    return np.argsort(np.abs(np.asarray(proba) - 0.5))[:n]


# ---------------------------------------------------------------- 5.1 metrics
def proportion_positive_predictions(y, score, target_tpr=0.8):
    """Jullum et al. PPP: proportion of observations predicted positive when the threshold is set to reach a
    pre-specified true positive rate. Lower is better (fewer alarms for the same recall)."""
    y, score = np.asarray(y), np.asarray(score)
    fpr, tpr, thr = roc_curve(y, score); t = thr[np.argmax(tpr >= target_tpr)]
    return float((score >= t).mean())


def cohens_kappa(y_true, y_pred): return float(cohen_kappa_score(y_true, y_pred))
