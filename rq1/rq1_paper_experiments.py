#!/usr/bin/env python3
"""RQ1 (paper version): test the recommendations of Jensen & Iosifidis (2023),
"Fighting Money Laundering with Statistics and Machine Learning" (IEEE Access 11, arXiv:2201.04207),
on the synthetic KYB data. The KYB task is *supervised client risk profiling* in the paper's terminology.

Paper claims tested (section numbers refer to the paper):
  P1 (5.1, 6)  accuracy is a poor metric under imbalance; use ROC / PR curves.
  P2 (5.1)     class imbalance should be handled (weighting, over/undersampling).
  P3 (4, 4.2)  supervised methods tend to beat unsupervised outlier detection.
  P4 (5.4)     interpretable models vs post-hoc explanation; do they agree?
  P5 (5.1)     ROC/PR ignore calibration -> check calibration under shift.
Run: python rq1_paper_experiments.py --train ... --test ... --out-dir out
"""
import argparse, json, re
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from rq1_book_vs_industry import (FEATS, Y, SEED, CAPACITY, prep, make, ap, precision_recall_at_k, pre)


def scores(model, X):
    return model.predict_proba(X)[:, 1]


def boot_delta(y, s_a, s_b, groups, n=500, seed=SEED):
    """Cluster bootstrap 95% CI of AP(a) - AP(b)."""
    rng = np.random.default_rng(seed); ug = np.unique(groups)
    idx = {g: np.where(groups == g)[0] for g in ug}; d = []
    for _ in range(n):
        ix = np.concatenate([idx[g] for g in rng.choice(ug, len(ug))])
        if y[ix].sum() == 0: continue
        d.append(ap(y[ix], s_a[ix]) - ap(y[ix], s_b[ix]))
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--train", required=True); a.add_argument("--test", required=True); a.add_argument("--out-dir", default="out")
    a = a.parse_args(); out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    tr, te = prep(pd.read_csv(a.train)), prep(pd.read_csv(a.test))
    Xtr, ytr, Xte, yte = tr[FEATS], tr[Y].to_numpy(), te[FEATS], te[Y].to_numpy()
    groups = te["group_id"].to_numpy(); R = {}

    lr = make("Logistic regression", C=0.1, class_weight="balanced").fit(Xtr, ytr)
    s_lr = scores(lr, Xte)

    # P1: accuracy vs ranking metrics
    p, r = precision_recall_at_k(yte, s_lr, CAPACITY)
    R["P1_metrics"] = dict(
        holdout_prevalence=float(yte.mean()),
        accuracy_all_negative_classifier=float(accuracy_score(yte, np.zeros_like(yte))),
        accuracy_logreg_at_0_5=float(accuracy_score(yte, (s_lr >= .5).astype(int))),
        logreg_ap=ap(yte, s_lr), logreg_roc_auc=float(roc_auc_score(yte, s_lr)),
        logreg_precision_at_capacity=p, logreg_recall_at_capacity=r,
        reading="If the all-negative classifier's accuracy is close to the model's, accuracy is uninformative (paper P1).")

    # P2: imbalance handling (fit-time only; holdout untouched)
    rng = np.random.default_rng(SEED); pos, neg = np.where(ytr == 1)[0], np.where(ytr == 0)[0]
    variants = {
        "none": (Xtr, ytr, dict(C=0.1, class_weight=None)),
        "class_weight=balanced": (Xtr, ytr, dict(C=0.1, class_weight="balanced")),
    }
    ov = np.concatenate([neg, pos, rng.choice(pos, len(neg) - len(pos), replace=True)])
    un = np.concatenate([pos, rng.choice(neg, len(pos), replace=False)])
    variants["random_oversampling"] = (Xtr.iloc[ov], ytr[ov], dict(C=0.1, class_weight=None))
    variants["random_undersampling"] = (Xtr.iloc[un], ytr[un], dict(C=0.1, class_weight=None))
    R["P2_imbalance"] = {}
    for k, (X_, y_, par) in variants.items():
        s = scores(make("Logistic regression", **par).fit(X_, y_), Xte)
        R["P2_imbalance"][k] = dict(holdout_ap=ap(yte, s), holdout_roc_auc=float(roc_auc_score(yte, s)))
    R["P2_note"] = "Training prevalence is 22.9%, so imbalance is mild; re-weighting mainly shifts calibration, not ranking."

    # P3: unsupervised (labels unused) vs supervised
    ct = pre("x").fit(Xtr); Ztr, Zte = ct.transform(Xtr), ct.transform(Xte)
    iso = IsolationForest(n_estimators=300, random_state=SEED).fit(Ztr); s_iso = -iso.score_samples(Zte)
    km = KMeans(n_clusters=7, n_init=10, random_state=SEED).fit(Ztr)  # K=7 as in Alexandre & Balsa (paper 3.1)
    s_km = km.transform(Zte).min(axis=1)
    R["P3_supervised_vs_unsupervised"] = {
        "Logistic regression (supervised)": dict(holdout_ap=ap(yte, s_lr), holdout_roc_auc=float(roc_auc_score(yte, s_lr))),
        "Isolation forest (unsupervised)": dict(holdout_ap=ap(yte, s_iso), holdout_roc_auc=float(roc_auc_score(yte, s_iso)),
                                                delta_ap_vs_logreg_ci95=boot_delta(yte, s_iso, s_lr, groups)),
        "K-means distance, K=7 (unsupervised)": dict(holdout_ap=ap(yte, s_km), holdout_roc_auc=float(roc_auc_score(yte, s_km)),
                                                     delta_ap_vs_logreg_ci95=boot_delta(yte, s_km, s_lr, groups)),
        "random_baseline_ap": float(yte.mean())}

    # P4: intrinsic vs post-hoc interpretability
    names = lr.named_steps["p"].get_feature_names_out()
    coef = pd.Series(lr.named_steps["m"].coef_[0], index=names)
    ebm = make("Explainable Boosting Machine", learning_rate=0.02, max_leaves=2).fit(Xtr, ytr)
    e = ebm.named_steps["m"]; tn = list(ebm.named_steps["p"].get_feature_names_out())
    # EBM was fitted on the preprocessed array -> terms are 'feature_0000'...; map back to transformed then original names
    ebm_imp = pd.Series(0.0, index=FEATS)
    for term, imp in zip(e.term_names_, e.term_importances()):
        idx = [int(x) for x in re.findall(r"feature_(\d+)", term)]
        for i in idx:  # interaction terms (none here, interactions=0) would split evenly
            orig = next(f for f in FEATS if tn[i].split("__", 1)[1].startswith(f))
            ebm_imp[orig] += imp / len(idx)
    xgb = make("XGBoost", learning_rate=0.05, max_depth=2, n_estimators=100).fit(Xtr, ytr)
    pi = permutation_importance(xgb, Xte, yte, scoring="average_precision", n_repeats=20, random_state=SEED)
    xgb_imp = pd.Series(pi.importances_mean, index=FEATS)
    # compare on original feature level: |coef| summed over one-hot levels for LR
    lr_feat = {f: float(sum(abs(v) for n_, v in coef.items() if n_.split("__", 1)[1].startswith(f))) for f in FEATS}
    lr_imp = pd.Series(lr_feat)
    ebm_feat = ebm_imp
    common = pd.DataFrame({"logreg_abs_coef": lr_imp, "ebm_importance": ebm_feat, "xgb_permutation_ap_drop": xgb_imp})
    R["P4_interpretability"] = dict(
        table=common.round(4).to_dict(),
        spearman_lr_vs_ebm=float(spearmanr(common.logreg_abs_coef, common.ebm_importance)[0]),
        spearman_lr_vs_xgb_permutation=float(spearmanr(common.logreg_abs_coef, common.xgb_permutation_ap_drop)[0]),
        reading="High rank agreement means the intrinsically interpretable model and post-hoc explanation tell the same story.")

    # P5: calibration under shift
    R["P5_calibration"] = {}
    for k, s in {"Logistic regression (balanced)": s_lr,
                 "Logistic regression (unweighted)": scores(make("Logistic regression", C=0.1, class_weight=None).fit(Xtr, ytr), Xte)}.items():
        R["P5_calibration"][k] = dict(mean_predicted=float(s.mean()), observed_rate=float(yte.mean()),
                                      brier=float(brier_score_loss(yte, s)))
    R["P5_calibration"]["brier_of_constant_prevalence_forecast"] = float(brier_score_loss(yte, np.full(len(yte), yte.mean())))

    json.dump(R, open(out / "rq1_paper_results.json", "w"), indent=2, default=float)
    print(json.dumps(R, indent=1, default=float))


if __name__ == "__main__":
    main()
