# The Promise Gap

Late deliveries, bad reviews and lost customers on the Olist marketplace. A funnel, cohort and
regression discontinuity analysis of 99,441 real orders, with a costed recommendation and
an experiment design.

**Question.** Do late deliveries cause bad reviews and lost repeat purchases on the Olist Brazilian
e-commerce marketplace, and what should Olist test to fix it?

**Answer.** Partly. Late orders get far more 1-star reviews (53.8% vs 6.6% on time), but missing the promise by one day is not the main cause. Once the trend is allowed for, the jump at the promise date is -1.7 pp (95% CI -4.9 pp to +1.5 pp). The damage builds over the following days: 13.0% 1-star on day 1, 42.5% on day 3, the point where most late customers are surveyed before the parcel arrives. There is no detectable effect on repeat purchase (+0.1 pp, CI -2.0 pp to +2.2 pp), and repeat purchase is so rare (2.0% within 180 days) that even the worst case is R$ 2,554 of order value a quarter.

**Recommendation.** Test a proactive delay message for orders that miss their date, with survey timing held the same in both arms. It needs 1,245 late orders per arm, about 5.7 months at 2017 to 2018 volumes. Separately, stop sending the review survey before the parcel arrives.

Dashboard: [docs/index.html](docs/index.html) (four pages: Funnel, Cohorts, Promise Gap, Experiment Plan).
One-page memo: [docs/memo.md](docs/memo.md).

## Limitations

Read these before the results.

- **The causal estimate is local.** The regression discontinuity measures what happens when an order
  misses its promise by about one day. It does not measure the effect of being a week late.
- **Two validity checks partly fail.** Fewer orders arrive just after the promise date than just before
  it (count ratio 0.68), and 3 of 14
  pre-delivery covariates jump at the line, including the promised delivery time. Orders just on time and
  just late are not perfectly comparable. Results are reported with that caveat.
- **Repeat purchase is too rare to measure well.** Only 2.0% of customers buy again within
  180 days. The repeat effect has a wide interval and cannot be told apart from zero.
- **Most late orders are reviewed before they arrive.** 74.5% of late-order reviews
  were sent before delivery. The 1-star rate of late orders partly measures "my parcel has not come".
- **No margin or commission data.** Money is order value paid by customers, not Olist revenue.
- **Old, bounded data.** Orders run from 2016-09-04 to 2018-08-29. Recent customers have less time to
  return. The all-time repeat rate is therefore a lower bound; the 180-day rate and the cohort curves
  use only customers and months that are fully observed.
- **The experiment is a design.** Nothing was run.

## What this shows

| Skill | Where |
|:--|:--|
| Data profiling and quality checks | `src/profile_data.py`, [docs/data_profile.md](docs/data_profile.md) |
| Layered SQL model (staging, intermediate, marts) | `sql/` |
| Choosing a grain and a customer key | `sql/intermediate/04_int_delivered_orders.sql`, [docs/exclusions.md](docs/exclusions.md) |
| Funnels with CTEs, conditional aggregation and GROUPING SETS | `sql/marts/02_mart_fulfilment_funnel.sql`, `sql/marts/03_mart_seller_funnel.sql` |
| Cohort retention with window functions and right censoring | `sql/marts/04_mart_customer_cohorts.sql`, `src/cohorts.py` |
| Causal inference (regression discontinuity) | `src/rd.py`, `src/promise_gap.py`, [docs/promise_gap_results.md](docs/promise_gap_results.md) |
| Business sizing with stated assumptions | `src/sizing.py`, [docs/assumptions.md](docs/assumptions.md) |
| Experiment design and power analysis | `src/experiment.py`, [docs/experiment_design.md](docs/experiment_design.md) |
| BI modelling (star schema, DAX) | `src/powerbi_export.py`, `powerbi/measures.dax`, [powerbi/POWERBI_BUILD_GUIDE.md](powerbi/POWERBI_BUILD_GUIDE.md) |
| Interactive dashboard | `src/dashboard.py`, [docs/index.html](docs/index.html) |
| Testing and verification | `tests/`, `src/verify.py` |
| Writing for decision makers | [docs/memo.md](docs/memo.md) |

## Key results

| Metric | Value |
|:--|--:|
| Orders in the data | 99,441 |
| Delivered orders (analysis grain) | 96,470 |
| Orders delivered (purchase to delivery) | 97.0% |
| Delivered orders that were late | 6.8% |
| Customers (customer_unique_id) | 93,350 |
| Repeat purchase rate, all customers, any time | 2.2% |
| Repeat purchase within 180 days (full window observed) | 2.0% |
| 1-star rate, on time vs late (all orders) | 6.6% vs 53.8% |
| RD jump in 1-star rate at the promise date | -1.7 pp (CI -4.9 pp to +1.5 pp) |
| 1-star rate, day 0 vs day 1 vs day 3 | 8.5%, 13.0%, 42.5% |
| RD jump in mean review score | -0.09 (CI -0.22 to +0.04) |
| RD jump in 180-day repeat purchase | +0.1 pp (CI -2.0 pp to +2.2 pp) |
| Repeat order value at risk per quarter (low / base / high) | R$ -2,846 / R$ -146 / R$ 2,554 |
| Leads that close / closed deals that ever sell | 10.5% / 44.7% |
| Experiment size (1-star, 10% relative drop) | 1,245 per arm, 5.7 months |

Negative money means the scenario implies late orders gain repeat value. See [docs/assumptions.md](docs/assumptions.md).

## Method

1. **Profile** every table: keys, join cardinality, nulls, duplicates, status and date coverage.
2. **Model** in DuckDB SQL. Staging casts types. The grain is one row per delivered order. Customers are
   `customer_unique_id`, because `customer_id` is created per order and would hide every repeat purchase.
   Every exclusion is logged with row counts.
3. **Funnels.** Fulfilment (purchased, approved, shipped, delivered, reviewed) by month and category.
   Seller acquisition (lead, closed deal, first sale, still selling 90 days later) by lead origin and segment.
4. **Cohorts.** Monthly acquisition cohorts. Cells not yet observable are left empty, and curves pool only
   observed cells, so recent cohorts do not drag retention down.
5. **Regression discontinuity.** Running variable: delivered date minus estimated date, in days. Local linear
   regression with a triangular kernel, bandwidth 4 days chosen by cross-validation, robustness at
   2 and 8 days, uniform kernel, donut, a day 1 vs day 0 comparison,
   placebo cutoffs, a density test and covariate balance.
6. **Sizing.** The repeat effect and its interval, times late first orders per quarter, times repeat order value.
7. **Experiment design.** Proactive delay message, randomised by customer, powered on measured baselines.
8. **Verification.** Core metrics rebuilt in pandas and matched to SQL, known-answer tests, and a check that
   every number in this README and the memo comes from `outputs/metrics.json`.

All choices and the reasons for them: [docs/DECISIONS.md](docs/DECISIONS.md).
Interview preparation: [docs/INTERVIEW_PREP.md](docs/INTERVIEW_PREP.md).

## How to reproduce

Requires Python 3.11 and a Kaggle account.

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows. On macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt

# Download the data (needs Kaggle credentials in ~/.kaggle/)
kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw --unzip
kaggle datasets download -d olistbr/marketing-funnel-olist -p data/raw --unzip

python run_all.py                 # rebuilds outputs/, docs/, README.md, powerbi/data/ and the notebook
pytest                            # known-answer tests
```

`data/raw/` must contain the eleven Olist CSV files. `run_all.py` deletes and rebuilds the DuckDB
warehouse each time, then runs the verification checks and fails loudly if any of them fail.

To publish the dashboard, enable GitHub Pages for the `docs/` folder on the main branch.

## Repository layout

```
sql/staging        typed, renamed views over the raw CSVs
sql/intermediate   reviews, order items, the delivered-order grain, exclusions
sql/marts          funnels, cohorts, the RD dataset
src/               Python steps called by run_all.py
tests/             pytest known-answer tests
outputs/           every computed table and metrics.json
docs/              memo, results, decisions, assumptions, experiment design, dashboard
powerbi/           measures.dax and the build guide (CSVs are generated into powerbi/data/)
notebooks/         executed walkthrough notebook
```

Data: Olist, Brazilian E-Commerce Public Dataset and Marketing Funnel dataset, Kaggle (CC BY-NC-SA 4.0).
