# Individual project: KYB ML vs rules, and industry comparison

**RQ1 basis (current): Jensen & Iosifidis (2023), "Fighting Money Laundering with Statistics and Machine Learning",
IEEE Access 11 (arXiv:2201.04207).** The earlier basis, Ananthaswamy's *Why Machines Learn*, was only available as a
48-page publisher sample (front matter, Ch.1, start of Ch.2) and is kept as secondary (`rq1/book_concept_map.csv`).

## Files (`rq1/`)
- `rq1_paper_experiments.py` - tests the paper's recommendations on the synthetic KYB data (metrics vs accuracy,
  imbalance handling, supervised vs unsupervised, interpretability agreement, calibration) -> `out/rq1_paper_results.json`
- `rq1_book_vs_industry.py` - five-model comparison (rules, LR, EBM, RF, XGBoost) + earlier book-concept experiments
- `paper_concept_map.csv`, `vendor_vs_paper.csv`, `vendor_matrix.csv` - paper findings mapped to local evidence and to
  ComplyCube, Onfido/Entrust, SmartSearch, Kyckr, PassFort (Moody's), ComplyAdvantage

## Console UI (`ui/`)
`ui/kyb_os.html` is a self-contained KYB-OS console (dashboard, UK map, case pipeline, ownership network, model comparison,
source vault) built from the project's own synthetic outputs. Rebuild with `python ui/build_data.py && python ui/build_map.py && python ui/build.py`
(`build_map.py` needs `shapely` and the GB local-authority GeoJSON from martinjc/UK-GeoJSON; Northern Ireland is not in that set).
Case locations on the map are simulated, not real addresses.

## Run
    pip install -r rq1/requirements.txt scipy
    cd rq1
    python rq1_book_vs_industry.py --train kyb_synthetic_train.csv --test kyb_synthetic_holdout.csv --reference demo_results.json --out-dir out
    python rq1_paper_experiments.py --train kyb_synthetic_train.csv --test kyb_synthetic_holdout.csv --out-dir out

## Caveats
- Data is synthetic. Training labels are produced by the scorecard; the holdout comes from a separate process, so CV
  scores (1.0 for the scorecard) are circular and every model drops ~0.7 AP from CV to holdout.
- Holdout has 41 positives: all model-vs-model differences have bootstrap CIs spanning 0.
- `compare_kyb.py` was not available; the five-model protocol is a reimplementation (rules scorecard AP matches the
  reference exactly, other models differ because grids were guessed).
- Vendor findings come from public marketing pages; no independent performance evidence was found.
