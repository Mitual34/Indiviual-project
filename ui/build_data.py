"""Builds ui/data.json for the KYB console from the project's own outputs (synthetic demo data only)."""
import json, csv, hashlib, sys, pathlib
import numpy as np, pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "rq1"))
from rq1_book_vs_industry import make, FEATS, Y, prep, rules_score

tr, te = prep(pd.read_csv(ROOT / "rq1/kyb_synthetic_train.csv")), prep(pd.read_csv(ROOT / "rq1/kyb_synthetic_holdout.csv"))
m = make("Logistic regression", C=0.1, class_weight="balanced").fit(tr[FEATS], tr[Y])
p = m.predict_proba(te[FEATS])[:, 1]; rank = (-p).argsort().argsort()          # 0 = riskiest
score = np.round(100 * (1 - rank / (len(p) - 1))).astype(int)
A = ["Harrow", "Ashgrove", "Brindle", "Calder", "Dunmore", "Elmstead", "Fenwick", "Garrow", "Hollin", "Ivelet", "Kestrel", "Lindon",
     "Marlow", "Norbury", "Oakhurst", "Pennine", "Quarry", "Redwick", "Saltmere", "Thornby", "Ullesby", "Verdun", "Wexcombe", "Yarrow"]
B = {"hospitality": ["Hospitality", "Catering", "Hotels"], "construction": ["Construction", "Build", "Civils"],
     "technology": ["Digital", "Systems", "Software"], "retail": ["Retail", "Trading", "Stores"]}
def name(cid, ind):
    h = int(hashlib.md5(cid.encode()).hexdigest(), 16); return f"{A[h % len(A)]} {B[ind][(h >> 8) % 3]} Ltd (demo)"
stage = lambda r: "decision" if r < 5 else "edd" if r < 20 else "review" if r < 60 else "screening" if r < 110 else "cleared"
cases = [dict(id=r.company_id, name=name(r.company_id, r.industry), sector=r.industry, age=float(r.company_age_years),
              status=r.company_status, late=None if pd.isna(r.late_filings) else int(r.late_filings), officers=int(r.officer_changes),
              flags=[int(r.jurisdiction_flag), int(r.pep_flag), int(r.sanctions_proximity_flag)], rules=int(rules_score(te.iloc[[i]])[0]),
              score=int(score[i]), stage=stage(int(rank[i])), asof=r.as_of_date) for i, r in enumerate(te.itertuples())]
cases.sort(key=lambda c: -c["score"])
res = json.load(open(ROOT / "rq1/out/rq1_results.json"))["models"]; pap = json.load(open(ROOT / "rq1/out/rq1_paper_results.json"))
models = [dict(name=k, ap=v["holdout_ap"], auc=v["holdout_roc_auc"], prec=v["precision_at_capacity"], rec=v["recall_at_capacity"],
               ci=v.get("delta_95_percent_ci")) for k, v in res.items()]
src = [dict(zip(["source", "layer", "status", "maps_to", "access"], [r[0], r[1], r[2], r[3], r[4]])) for r in list(csv.reader(open(ROOT / "kyb_ingest/source_registry.csv")))[1:]]
out = dict(cases=cases, models=models, prevalence=float(te[Y].mean()), capacity=60, holdout_n=len(te), positives=int(te[Y].sum()),
           paper=dict(acc_null=pap["P1_metrics"]["accuracy_all_negative_classifier"], acc_lr=pap["P1_metrics"]["accuracy_logreg_at_0_5"],
                      iso_ap=pap["P3_supervised_vs_unsupervised"]["Isolation forest (unsupervised)"]["holdout_ap"],
                      lr_ap=pap["P3_supervised_vs_unsupervised"]["Logistic regression (supervised)"]["holdout_ap"],
                      mean_pred=pap["P5_calibration"]["Logistic regression (balanced)"]["mean_predicted"], brier=pap["P5_calibration"]["Logistic regression (balanced)"]["brier"],
                      brier_const=pap["P5_calibration"]["brier_of_constant_prevalence_forecast"], sp_ebm=pap["P4_interpretability"]["spearman_lr_vs_ebm"]),
           sources=src)
json.dump(out, open(pathlib.Path(__file__).parent / "data.json", "w"), separators=(",", ":"))
from collections import Counter; print(Counter(c["stage"] for c in cases), len(src), cases[0])
