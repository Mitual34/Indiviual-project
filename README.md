# Individual project: KYB ML vs rules, and industry comparison

`rq1/` holds RQ1: how the ML ideas in Ananthaswamy's *Why Machines Learn* compare with KYB/AML industry tooling
(ComplyCube, Onfido/Entrust, SmartSearch, Kyckr, PassFort/Moody's, ComplyAdvantage).

Run:
    pip install -r rq1/requirements.txt
    python rq1/rq1_book_vs_industry.py --train rq1/kyb_synthetic_train.csv --test rq1/kyb_synthetic_holdout.csv \
        --reference rq1/demo_results.json --out-dir rq1/out

Caveats: data is synthetic; the five-model protocol is a reimplementation (rules scorecard AP matches the reference
exactly, other models differ because hyperparameter grids were guessed); vendor matrix is from public marketing pages
and has no independent performance evidence; book mapping beyond the sample's contents/prologue/Ch.1 is from chapter titles.
