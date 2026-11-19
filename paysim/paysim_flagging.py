"""Suspicious-behaviour flagging on PaySim-style mobile-money transactions (Jensen & Iosifidis 2023, Sec 2.2 / 4).
Schema follows Data_Dictionary.txt: step (1 step = 1 hour, 744 steps), type, amount, nameOrig, oldbalanceOrg,
newbalanceOrig, nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud.

Notes on the data (from the dictionary): balances are unavailable for merchant recipients (names starting 'M');
isFlaggedFraud is a built-in rule (a single transfer above 200,000) so it is the natural rules baseline.
Caveat to keep in mind when reading results: PaySim is simulated, and balance-arithmetic features can be
unrealistically predictive because the simulator's fraud mechanism (take over account, empty it, cash out) leaves
a clean balance signature. High scores here do NOT transfer to real transaction data.
"""
from __future__ import annotations
import argparse, json, sys, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rq1"))
from aml_methods import LogisticRegressionGD, balanced_weights, outlier_ensemble, proportion_positive_predictions  # noqa: E402
from sklearn.ensemble import IsolationForest  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402

COLS = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig", "nameDest", "oldbalanceDest",
        "newbalanceDest", "isFraud", "isFlaggedFraud"]
TYPES = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]
FEATURES = ["amount", "log_amount", "err_orig", "err_dest", "orig_emptied", "dest_merchant", "hour", "day",
            "dest_balance_zero_before", *[f"type_{t}" for t in TYPES]]


def load(path, nrows=None) -> pd.DataFrame:
    df = pd.read_csv(path, nrows=nrows)
    missing = set(COLS) - set(df.columns)
    if missing: raise ValueError(f"missing columns: {sorted(missing)}")
    return df[COLS]


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Row-wise features only (no look-ahead). Merchant recipients have no balance information, so their
    destination-balance features are NaN, not 0."""
    d = df.copy(); d["type"] = d["type"].str.upper().str.replace("-", "_", regex=False)
    f = pd.DataFrame(index=d.index)
    f["amount"] = d["amount"]; f["log_amount"] = np.log1p(d["amount"])
    f["err_orig"] = d["newbalanceOrig"] + d["amount"] - d["oldbalanceOrg"]      # 0 for a consistent debit
    merch = d["nameDest"].astype(str).str.startswith("M")
    f["err_dest"] = (d["oldbalanceDest"] + d["amount"] - d["newbalanceDest"]).where(~merch)
    f["orig_emptied"] = ((d["newbalanceOrig"] == 0) & (d["oldbalanceOrg"] > 0)).astype(int)
    f["dest_merchant"] = merch.astype(int)
    f["dest_balance_zero_before"] = (d["oldbalanceDest"] == 0).where(~merch).astype(float)
    f["hour"] = d["step"] % 24; f["day"] = d["step"] // 24
    for t in TYPES: f[f"type_{t}"] = (d["type"] == t).astype(int)
    return f[FEATURES]


def temporal_split(df: pd.DataFrame, train_frac_steps=0.7, drop_seen_accounts=True):
    """Chronological split on `step`. With drop_seen_accounts, test rows whose originator already appears in the
    training window are removed (account-level leakage guard, analogous to the group-ID rule in the KYB data)."""
    cut = int(df["step"].max() * train_frac_steps)
    tr, te = df[df["step"] <= cut], df[df["step"] > cut]
    if drop_seen_accounts: te = te[~te["nameOrig"].isin(set(tr["nameOrig"]))]
    return tr, te, cut


def _prep(Ftr, Fte):
    med = Ftr.median(numeric_only=True).fillna(0)
    a, b = Ftr.fillna(med), Fte.fillna(med)
    mu, sd = a.mean(), a.std().replace(0, 1)
    return ((a - mu) / sd).to_numpy(), ((b - mu) / sd).to_numpy(), a, b


def precision_at_k(y, s, k):
    return float(np.asarray(y)[np.argsort(-np.asarray(s), kind="stable")[:k]].mean())


def evaluate(df: pd.DataFrame, capacity_frac=0.001, seed=0, max_train=200_000, models=("rules", "logreg", "isolation_forest", "outlier_ensemble")):
    tr, te, cut = temporal_split(df)
    ytr, yte = tr["isFraud"].to_numpy(), te["isFraud"].to_numpy()
    if len(tr) > max_train:   # keep the most recent training window if very large
        tr = tr.iloc[-max_train:]; ytr = ytr[-max_train:]
    Ftr, Fte = make_features(tr), make_features(te)
    Ztr, Zte, _, _ = _prep(Ftr, Fte); k = max(1, int(len(te) * capacity_frac)); out = dict(
        train_rows=len(tr), test_rows=len(te), cut_step=cut, test_fraud=int(yte.sum()), test_prevalence=float(yte.mean()), capacity_k=k)
    scores = {}
    if "rules" in models:
        scores["Rules: isFlaggedFraud (>200k transfer)"] = te["isFlaggedFraud"].to_numpy().astype(float)
    if "logreg" in models and ytr.sum() > 0:
        m = LogisticRegressionGD(l2=1e-2).fit(Ztr, ytr, balanced_weights(ytr)); scores["Weighted logistic regression"] = m.predict_proba(Zte)
    if "isolation_forest" in models:
        scores["Isolation forest (unsupervised)"] = -IsolationForest(n_estimators=200, random_state=seed).fit(Ztr).score_samples(Zte)
    if "outlier_ensemble" in models:
        sub = Ztr[np.random.default_rng(seed).choice(len(Ztr), min(len(Ztr), 5000), replace=False)]  # OCSVM is O(n^2)
        scores["Outlier ensemble (IF+OCSVM+GMM, unsupervised)"] = outlier_ensemble(sub, Zte, seed=seed)[0]
    out["models"] = {}
    for name, s in scores.items():
        ok = yte.sum() > 0 and yte.sum() < len(yte)
        out["models"][name] = dict(
            ap=float(average_precision_score(yte, s)) if ok else None, roc_auc=float(roc_auc_score(yte, s)) if ok else None,
            precision_at_k=precision_at_k(yte, s, k), recall_at_k=float(yte[np.argsort(-s, kind="stable")[:k]].sum() / max(yte.sum(), 1)),
            ppp_at_tpr80=proportion_positive_predictions(yte, s, 0.8) if ok else None)
    return out


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--csv", required=True); a.add_argument("--nrows", type=int); a.add_argument("--out", default="paysim_results.json")
    a = a.parse_args(); res = evaluate(load(a.csv, a.nrows)); json.dump(res, open(a.out, "w"), indent=2); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
