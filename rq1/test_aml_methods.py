"""Sanity tests on small generated toy arrays only. No KYB data is read here."""
import numpy as np
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from aml_methods import *

rng = np.random.default_rng(0)

def blobs(n=60):
    return np.vstack([rng.normal(c, .3, (n, 2)) for c in ((0, 0), (5, 5), (0, 5))])

def test_kmeans_recovers_blobs_and_matches_sklearn_objective():
    X = blobs(); best = min(kmeans(X, 3, seed=s)[2] for s in range(5))
    sk = KMeans(3, n_init=10, random_state=0).fit(X).inertia_
    assert abs(best - sk) / sk < 1e-6

def test_fuzzy_cmeans_memberships_sum_to_one_and_find_centres():
    X = blobs(); V, U = fuzzy_cmeans(X, 3)
    assert np.allclose(U.sum(1), 1)
    for c in ((0, 0), (5, 5), (0, 5)): assert np.min(np.linalg.norm(V - c, axis=1)) < .3

def test_pca_matches_eigendecomposition_and_is_orthonormal():
    X = rng.normal(size=(300, 4)) @ np.diag([5, 2, 1, .1]); comp, var, mean = pca(X, 2)
    assert np.allclose(comp @ comp.T, np.eye(2), atol=1e-8)
    assert np.allclose(var, np.sort(np.linalg.eigvalsh(np.cov(X, rowvar=False)))[::-1][:2])

def test_autoencoder_reduces_loss_and_flags_outlier():
    z = rng.normal(size=(200, 2)); X = np.c_[z, z @ rng.normal(size=(2, 4))]  # rank-2 data in 6-d
    ae = Autoencoder((6, 3, 6), epochs=800, lr=.02).fit(X)
    assert ae.loss_[-1] < .3 * ae.loss_[0]
    out = rng.normal(size=(1, 6)) * 4; assert ae.score(out)[0] > np.median(ae.score(X))

def test_logistic_gd_matches_sklearn_and_weights_shift_intercept():
    X = rng.normal(size=(400, 3)); y = (X @ [1, -2, .5] + rng.logistic(size=400) > 0).astype(int)
    ours = LogisticRegressionGD(l2=1e-6).fit(X, y)
    ref = LogisticRegression(C=1e6, max_iter=5000).fit(X, y)
    assert np.allclose(ours.coef_, ref.coef_[0], atol=2e-2)
    Xi = rng.normal(size=(500, 2)); yi = (rng.random(500) < .1).astype(int)
    assert LogisticRegressionGD().fit(Xi, yi, balanced_weights(yi)).intercept_ > LogisticRegressionGD().fit(Xi, yi).intercept_

def test_outlier_ensemble_ranks_planted_outliers_high():
    X = rng.normal(size=(300, 3)); far = rng.normal(8, .2, (5, 3))
    ens, parts = outlier_ensemble(X, np.vstack([X[:50], far]))
    assert ens[-5:].min() > np.quantile(ens[:50], .9) and set(parts) == {"isolation_forest", "one_class_svm", "gaussian_mixture"}

def _imb():
    X = np.vstack([rng.normal(0, 1, (200, 2)), rng.normal(2, .5, (20, 2))]); y = np.r_[np.zeros(200), np.ones(20)].astype(int); return X, y

def test_resamplers_balance_classes_and_synthetic_points_stay_in_minority_hull_box():
    X, y = _imb()
    for f in (random_oversample, random_undersample, smote):
        Xr, yr = f(X, y); assert (yr == 1).sum() == (yr == 0).sum()
    Xs, ys = smote(X, y); new = Xs[len(X):]; m = X[y == 1]
    assert (new >= m.min(0) - 1e-9).all() and (new <= m.max(0) + 1e-9).all()
    Xa, ya = adasyn(X, y); assert len(Xa) >= len(X) and abs((ya == 1).sum() - 200) <= 25
    Xb, yb = borderline_smote(X, y); assert len(Xb) >= len(X)

def test_benford_accepts_lognormal_spread_rejects_uniform_leading_digits():
    good = benford_features(10 ** rng.uniform(0, 6, 5000)); bad = benford_features(rng.integers(100, 999, 5000))
    assert good["p_value"] > .01 and bad["p_value"] < 1e-6 and good["mad"] < bad["mad"]

def test_ppp_and_kappa_and_uncertainty_sampling():
    y = np.r_[np.ones(50), np.zeros(450)].astype(int); good = y + rng.normal(0, .3, 500); rand = rng.random(500)
    assert proportion_positive_predictions(y, good) < proportion_positive_predictions(y, rand)
    assert cohens_kappa([0, 1, 1, 0], [0, 1, 1, 0]) == 1.0
    assert list(uncertainty_sampling([.1, .52, .9, .45], 2)) == [3, 1] or set(uncertainty_sampling([.1, .52, .9, .45], 2)) == {1, 3}
