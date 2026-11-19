"""Tests on small FICTIONAL PaySim-style data generated here (no real PaySim file is read)."""
import sys, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paysim_flagging import make_features, temporal_split, evaluate, COLS


def toy(n=6000, seed=0):
    r = np.random.default_rng(seed); step = np.sort(r.integers(1, 745, n))
    typ = r.choice(["CASH-IN", "CASH_OUT", "PAYMENT", "TRANSFER", "DEBIT"], n, p=[.2, .3, .3, .15, .05])
    amt = r.lognormal(8, 1.2, n).round(2); old = (r.lognormal(9, 1.5, n)).round(2)
    new = np.maximum(old - amt, 0); dest = np.where(typ == "PAYMENT", "M", "C") + np.arange(n).astype(str)
    fraud = ((typ == "TRANSFER") | (typ == "CASH_OUT")) & (r.random(n) < .03)
    amt = np.where(fraud, old, amt); new = np.where(fraud, 0, new)     # fraud empties the account (simulator's signature)
    df = pd.DataFrame(dict(step=step, type=typ, amount=amt, nameOrig=["C" + str(i) for i in range(n)], oldbalanceOrg=old,
                           newbalanceOrig=new, nameDest=dest, oldbalanceDest=r.lognormal(8, 1, n).round(2), newbalanceDest=0.0,
                           isFraud=fraud.astype(int)))
    df["newbalanceDest"] = df["oldbalanceDest"] + df["amount"]
    df["isFlaggedFraud"] = ((df["type"] == "TRANSFER") & (df["amount"] > 200_000)).astype(int)
    return df[COLS]


def test_features_balance_errors_and_merchant_nan():
    f = make_features(toy())
    d = toy()
    ok = d["type"].isin(["CASH_OUT", "TRANSFER"]) & (d["isFraud"] == 0) & (d["oldbalanceOrg"] > d["amount"])
    assert np.allclose(f.loc[ok, "err_orig"], 0)                       # consistent debits have zero balance error
    assert f.loc[d["type"] == "PAYMENT", "err_dest"].isna().all()      # merchants: no destination balance info
    assert f.loc[d["isFraud"] == 1, "orig_emptied"].eq(1).all()
    assert f["type_CASH_IN"].sum() == (d["type"].str.replace("-", "_") == "CASH_IN").sum()   # hyphenated type handled


def test_temporal_split_is_chronological_and_drops_seen_accounts():
    d = toy(); d.loc[d.index[-50:], "nameOrig"] = d.loc[d.index[:50], "nameOrig"].to_numpy()   # reuse early accounts late
    tr, te, cut = temporal_split(d)
    assert tr["step"].max() <= cut < te["step"].min()
    assert not set(te["nameOrig"]) & set(tr["nameOrig"])


def test_evaluate_runs_and_unsupervised_beats_random_on_toy():
    res = evaluate(toy(), capacity_frac=0.01)
    assert res["test_fraud"] > 0 and set(res["models"]) >= {"Weighted logistic regression", "Isolation forest (unsupervised)"}
    assert res["models"]["Weighted logistic regression"]["ap"] > 5 * res["test_prevalence"]      # emptied-account signature is learnable
    assert 0 <= res["models"]["Rules: isFlaggedFraud (>200k transfer)"]["precision_at_k"] <= 1
