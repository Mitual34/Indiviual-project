#!/usr/bin/env python3
"""RQ1: How does the ML theory in Ananthaswamy's *Why Machines Learn* compare with
what already exists in industry KYB/AML tooling?

Two evidence layers:
  A. EMPIRICAL  - reproduces the five-model KYB comparison on the synthetic CSVs
                  (rules scorecard, logistic regression, EBM, random forest, XGBoost)
                  and adds experiments for book concepts that can be tested here
                  (perceptron / linear separability, bias-variance, shift).
  B. QUALITATIVE - vendor_matrix.csv (ComplyCube, Onfido, SmartSearch, Kyckr,
                  PassFort, ComplyAdvantage) is read and joined to the book concepts.

Usage:
  python rq1_book_vs_industry.py --train TRAIN.csv --test HOLDOUT.csv \
      --reference demo_results.json --out-dir out
NOTE: compare_kyb.py was not available when this was written; the protocol is
re-implemented from demo_results.json, so numbers are checked against it, not assumed.
"""
import argparse, json, itertools, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression, Perceptron
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier
from interpret.glassbox import ExplainableBoostingClassifier

warnings.filterwarnings("ignore")
SEED = 7
NUM = ["company_age_years", "late_filings", "officer_changes"]
FLAGS = ["jurisdiction_flag", "pep_flag", "sanctions_proximity_flag"]
CAT = ["industry", "company_status"]
FEATS = NUM + FLAGS + CAT
Y = "edd_label"
CAPACITY = 60
RULE_W = {"jurisdiction_flag": 3, "pep_flag": 4, "sanctions_proximity_flag": 5}  # from demo_results.json


# ---------- helpers ----------
def prep(df):
    return df.sort_values(["as_of_date", "company_id"]).reset_index(drop=True)

def rules_score(df):
    return sum(w * df[c].to_numpy() for c, w in RULE_W.items()).astype(float)

def precision_recall_at_k(y, s, k, rng_draws=200, seed=0):
    """Expected precision/recall at top-k with ties broken at random (averaged)."""
    rng = np.random.default_rng(seed); y = np.asarray(y); s = np.asarray(s)
    ps = []
    for _ in range(rng_draws):
        order = np.lexsort((rng.random(len(s)), -s))
        ps.append(y[order[:k]].sum())
    hits = np.mean(ps)
    return hits / k, hits / max(y.sum(), 1)

def ap(y, s):
    return float(average_precision_score(y, s))

def pre(model_kind):
    num = Pipeline([("i", SimpleImputer(strategy="median")), ("s", StandardScaler())])
    ct = ColumnTransformer([("n", num, NUM + FLAGS), ("c", OneHotEncoder(handle_unknown="ignore"), CAT)])
    return ct

def make(kind, **p):
    if kind == "Logistic regression":
        return Pipeline([("p", pre(kind)), ("m", LogisticRegression(max_iter=2000, random_state=SEED, **p))])
    if kind == "Random Forest":
        return Pipeline([("p", pre(kind)), ("m", RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=2, **p))])
    if kind == "XGBoost":
        return Pipeline([("p", pre(kind)), ("m", XGBClassifier(random_state=SEED, n_jobs=2, eval_metric="logloss", **p))])
    if kind == "Explainable Boosting Machine":
        return Pipeline([("p", pre(kind)), ("m", ExplainableBoostingClassifier(random_state=SEED, n_jobs=1, interactions=0, **p))])
    raise ValueError(kind)

GRIDS = {
    "Logistic regression": [dict(C=c, class_weight=w) for c in (0.01, 0.1, 1, 10) for w in (None, "balanced")],
    "Explainable Boosting Machine": [dict(learning_rate=lr, max_leaves=ml) for lr in (0.01, 0.02, 0.05) for ml in (2, 3)],
    "Random Forest": [dict(max_depth=d, min_samples_leaf=l) for d in (2, 4, 8) for l in (3, 10)],
    "XGBoost": [dict(learning_rate=lr, max_depth=d, n_estimators=n) for lr in (0.05, 0.1) for d in (2, 3) for n in (100, 200)],
}

def expanding_folds(n, step=300, n_folds=4):
    return [(np.arange(0, step * (i + 1)), np.arange(step * (i + 1), step * (i + 2))) for i in range(n_folds)]

def cv_ap(kind, params, X, y, folds):
    out = []
    for fit, val in folds:
        m = make(kind, **params).fit(X.iloc[fit], y[fit])
        out.append(ap(y[val], m.predict_proba(X.iloc[val])[:, 1]))
    return float(np.mean(out))


# ---------- A1: five-model comparison ----------
def five_model(train, test, boot=1000):
    Xtr, ytr = train[FEATS], train[Y].to_numpy()
    Xte, yte = test[FEATS], test[Y].to_numpy()
    folds = expanding_folds(len(train))
    res, hold_scores = {}, {}
    s_rules_tr = rules_score(train); s_rules_te = rules_score(test)
    p, r = precision_recall_at_k(yte, s_rules_te, CAPACITY)
    res["Rules scorecard"] = dict(
        mean_cv_ap=float(np.mean([ap(ytr[v], s_rules_tr[v]) for _, v in folds])),
        parameters=RULE_W, holdout_ap=ap(yte, s_rules_te), holdout_roc_auc=float(roc_auc_score(yte, s_rules_te)),
        precision_at_capacity=p, recall_at_capacity=r)
    hold_scores["Rules scorecard"] = s_rules_te
    for kind, grid in GRIDS.items():
        best = max(grid, key=lambda g: cv_ap(kind, g, Xtr, ytr, folds))
        cvs = cv_ap(kind, best, Xtr, ytr, folds)
        m = make(kind, **best).fit(Xtr, ytr)
        s = m.predict_proba(Xte)[:, 1]; hold_scores[kind] = s
        p, r = precision_recall_at_k(yte, s, CAPACITY)
        res[kind] = dict(mean_cv_ap=cvs, parameters=best, holdout_ap=ap(yte, s),
                         holdout_roc_auc=float(roc_auc_score(yte, s)), precision_at_capacity=p, recall_at_capacity=r)
        print(f"  fitted {kind}: {best}")
    # cluster bootstrap over group_id of delta AP vs rules
    rng = np.random.default_rng(SEED)
    groups = test["group_id"].to_numpy(); ug = np.unique(groups)
    idx_by_g = {g: np.where(groups == g)[0] for g in ug}
    draws = {k: [] for k in hold_scores if k != "Rules scorecard"}
    for _ in range(boot):
        pick = rng.choice(ug, len(ug), replace=True)
        ix = np.concatenate([idx_by_g[g] for g in pick]); yb = yte[ix]
        if yb.sum() == 0: continue
        base = ap(yb, hold_scores["Rules scorecard"][ix])
        for k in draws: draws[k].append(ap(yb, hold_scores[k][ix]) - base)
    for k, d in draws.items():
        res[k]["holdout_ap_delta_vs_rules"] = res[k]["holdout_ap"] - res["Rules scorecard"]["holdout_ap"]
        res[k]["delta_95_percent_ci"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
        res[k]["valid_bootstrap_draws"] = len(d)
    return res, hold_scores


# ---------- A2: book-concept experiments ----------
def concept_experiments(train, test, five):
    out = {}
    ytr, yte = train[Y].to_numpy(), test[Y].to_numpy()
    # (1) Ch.1/2 - perceptron convergence needs linear separability. Is the TRAIN label separable in the flags?
    Xf = train[FLAGS].to_numpy()
    per = Perceptron(max_iter=5000, tol=None, random_state=SEED).fit(Xf, ytr)
    out["perceptron_train_accuracy_on_flags"] = float((per.predict(Xf) == ytr).mean())
    out["perceptron_note"] = ("1.0 means the training labels are linearly separable in the three flags and the perceptron "
                              "convergence theorem applies; <1.0 means it does not.")
    # (2) Ch.1 'learn the weights' - recover scorecard weights from train labels via logistic regression
    lr = LogisticRegression(C=100, max_iter=5000).fit(Xf, ytr)
    out["logreg_weights_on_flags_train"] = dict(zip(FLAGS, map(float, lr.coef_[0])))
    out["scorecard_weights"] = RULE_W
    # (3) circularity: train labels vs scorecard
    s = rules_score(train)
    out["train_label_vs_scorecard_ap"] = ap(ytr, s)
    out["train_positive_rate"] = float(ytr.mean()); out["holdout_positive_rate"] = float(yte.mean())
    # (4) Ch.12 bias-variance: CV(train) vs holdout gap per model
    out["cv_minus_holdout_ap"] = {k: v["mean_cv_ap"] - v["holdout_ap"] for k, v in five.items()}
    # (5) learning curve: logistic regression AP on holdout vs train size
    lc = {}
    for n in (150, 300, 600, 900, 1200, 1500):
        m = make("Logistic regression", C=0.1, class_weight="balanced").fit(train[FEATS].iloc[:n], ytr[:n])
        lc[n] = ap(yte, m.predict_proba(test[FEATS])[:, 1])
    out["logreg_holdout_ap_by_train_size"] = lc
    # (6) shift: do flags carry different signal in train vs holdout?
    out["holdout_positive_rate_by_flag"] = {c: {str(v): float(test.loc[test[c] == v, Y].mean()) for v in (0, 1)} for c in FLAGS}
    out["train_positive_rate_by_flag"] = {c: {str(v): float(train.loc[train[c] == v, Y].mean()) for v in (0, 1)} for c in FLAGS}
    # (7) random baseline
    out["random_ap_baseline"] = float(yte.mean())
    return out


def compare_reference(mine, ref_path):
    ref = json.load(open(ref_path))["models"]; rows = []
    for k, v in ref.items():
        if k in mine:
            rows.append(dict(model=k, ref_holdout_ap=v["holdout_ap"], my_holdout_ap=mine[k]["holdout_ap"],
                             ref_prec_at_cap=v["precision_at_capacity"], my_prec_at_cap=mine[k]["precision_at_capacity"],
                             ref_params=json.dumps(v["parameters"]), my_params=json.dumps(mine[k]["parameters"])))
    return pd.DataFrame(rows)


def plots(five, exp, out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    names = list(five); ap_ = [five[n]["holdout_ap"] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(names, ap_, color="#4c78a8"); ax.axhline(exp["random_ap_baseline"], ls="--", c="grey", label="random (prevalence)")
    for i, n in enumerate(names):
        ci = five[n].get("delta_95_percent_ci")
        if ci: ax.text(i, ap_[i] + .005, f"Δ vs rules\n[{ci[0]:+.2f},{ci[1]:+.2f}]", ha="center", fontsize=7)
    ax.set_ylabel("Holdout average precision"); ax.legend(); plt.xticks(rotation=20, ha="right")
    ax.set_title("Holdout AP: no model reliably beats the rules (CIs span 0)"); plt.tight_layout(); plt.savefig(out / "fig_holdout_ap.png", dpi=150); plt.close()
    lc = exp["logreg_holdout_ap_by_train_size"]
    fig, ax = plt.subplots(figsize=(6, 3.6)); ax.plot(list(lc), list(lc.values()), "o-")
    ax.axhline(exp["random_ap_baseline"], ls="--", c="grey"); ax.set_xlabel("training rows"); ax.set_ylabel("holdout AP")
    ax.set_title("Learning curve (logistic regression)"); plt.tight_layout(); plt.savefig(out / "fig_learning_curve.png", dpi=150); plt.close()


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--train", required=True); ap_.add_argument("--test", required=True)
    ap_.add_argument("--reference"); ap_.add_argument("--out-dir", default="out")
    ap_.add_argument("--bootstrap", type=int, default=1000)
    a = ap_.parse_args(); out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    train, test = prep(pd.read_csv(a.train)), prep(pd.read_csv(a.test))
    assert not set(train.group_id) & set(test.group_id), "group leakage between train and holdout"
    print("A1: five-model comparison"); five, _ = five_model(train, test, a.bootstrap)
    print("A2: concept experiments"); exp = concept_experiments(train, test, five)
    json.dump(dict(models=five, concept_experiments=exp, dataset="synthetic demonstration"), open(out / "rq1_results.json", "w"), indent=2)
    if a.reference:
        cmp_ = compare_reference(five, a.reference); cmp_.to_csv(out / "reproduction_check.csv", index=False); print(cmp_.to_string())
    plots(five, exp, out); print(json.dumps(exp, indent=1))


if __name__ == "__main__":
    main()
