# Decisions

Each entry: the choice, the alternatives, and why. Grouped by section.

## Setup

- **Kaggle download used `~/.kaggle/access_token`, not `kaggle.json`.** The brief named `kaggle.json`.
  That file did not exist. The machine had the newer Kaggle CLI token file, which the CLI reads
  the same way. The owner approved continuing ("build in one go").
- **Package versions are pinned to what was installed on the build date.** `requirements.txt`
  lists exact versions.
- **Git commits use the owner's identity only.** No co-author lines.

## Data model

- **Analysis grain: one row per delivered order.** "Delivered" means status is `delivered`
  AND a delivery timestamp exists. Status alone is not enough (8 delivered orders have no date).
- **Customer = `customer_unique_id`.** `customer_id` is generated per order. Using it would
  make every customer a one-time buyer and the repeat rate would be zero by construction.
- **One review per order: the latest answered.** 547 orders have several reviews. The latest
  answer is the customer's final view. Ties broken by `review_id` so the build is deterministic.
- **One category and one seller per order: those of the most expensive item.** Orders with
  several products need a single label for funnel and balance tables. Price is the best proxy for
  what the order was "about". Ties go to the lowest item number.
- **Missing category is labelled `unknown`, orders without items are `no_items`.** Dropping them
  would hide 775 orders from the funnel, which is exactly where they matter.
- **A purchase means a delivered order, everywhere.** Customer cohorts, repeat purchase and seller
  activity all count delivered orders. This keeps every metric on the same grain.
- **A repeat purchase is a delivered order on a later calendar day.** Same-day extra orders
  (890 of them) look like one shopping session split into several orders, not a return visit.
- **Data end = last purchase date among delivered orders (2018-08-29).** 20 orders placed after
  that were never delivered and are not usable. All censoring rules use this date.
- **A month is "observed" only if all its days are inside the data.** August 2018 ends on the
  29th, so the last complete month is July 2018. This is stricter than including August, and
  avoids a small artificial drop in the last cohort cell.
- **Cohorts start in January 2017.** 2016 has 329 orders and a two-month gap. Customers first
  seen in 2016 are still known, so they are not counted as new in 2017.

## Funnels

- **Fulfilment stages are defined by timestamps, made cumulative.** An order reaches "approved"
  if it has an approval time or reached any later stage. 14 delivered orders lack an approval
  time; a delivered order was obviously approved.
- **"Delivered" in the funnel = the analysis grain definition**, so the funnel and the rest of
  the project agree on the count.
- **"Reviewed" = delivered and has a review.** Reviews on canceled orders exist but are not part of
  the fulfilment path.
- **Seller funnel by business segment starts at "closed deal".** Segment is only recorded when a
  deal closes, so lead counts by segment do not exist.
- **"Still selling 90 days later" = a delivered sale on or after first sale + 90 days, measured
  only for sellers whose first sale is at least 90 days before data end.** Others are reported as
  censored, not as failures.

## Promise gap (regression discontinuity)

- **Running variable in whole days: delivered date minus estimated date.** The estimate is a
  date with no time. A parcel that arrives at 18:00 on the promised day is on time. Fractional
  days would call it late.
- **Cutoff sits between day 0 (on time) and day 1 (first late day).** The regression is centered
  at 0.5 so the jump is measured exactly between the two.
- **Local linear regression with a triangular kernel.** Standard choice for RD. The triangular
  kernel gives the most weight to days closest to the promise date.
- **Bandwidth chosen by leave-one-out cross-validation (Ludwig and Miller style).** For each
  candidate bandwidth, each day near the cutoff is predicted from a line fitted only on days
  further from the cutoff on the same side. The bandwidth with the smallest prediction error on
  the primary outcome (1-star rate) wins. It is easy to explain and does not need a package.
  The same bandwidth is used for all outcomes; robustness at half and double covers sensitivity.
- **Robust (HC1) standard errors.** Clustering on the running variable is known to perform badly
  with few distinct values (Kolesar and Rothe 2018), so it is not used.
- **Placebo cutoffs at one bandwidth below and one bandwidth above the real cutoff,** using only
  data on one side of the real cutoff so the real jump cannot leak in.
- **Density check: Poisson regression of daily order counts with a jump term.** A McCrary-style
  test that is easy to explain.
- **Donut RD added because the density check fails.** Fewer orders arrive one day late than the
  trend predicts. A donut that drops days 0 and 1 shows whether the result depends on the orders
  right at the line.
- **A day 1 vs day 0 comparison is reported next to the local linear RD.** The outcome curve rises
  steeply right after the line, and a local linear fit gives that slope much of the change. Comparing
  the two adjacent days (the local randomisation view of RD) shows the other side of the trade-off.
  Neither is presented as the single truth; both are shown with their assumptions.
- **Survey-timing curve added.** The profile showed most late orders are reviewed before they
  arrive. Plotting that share by days late explains where the 1-star ramp comes from.
- **Repeat outcome uses first orders only, with a full 180-day window.** See exclusions.md.
- **Covariate balance includes a "predicted 1-star" index.** Each covariate is tested on its own,
  and also all at once by predicting the outcome from covariates and testing that prediction for a jump.

## Business sizing

- **Money is order value (items plus freight) paid by customers.** Olist's commission is not in the
  data, so its own revenue cannot be computed.
- **Base quarter: 2018 Q2,** the most recent complete quarter.

## Outputs

- **Power BI CSVs are not committed.** They are large and are rebuilt by `run_all.py`.
- **README and memo are rendered from templates in `docs/templates/`.** Every number is filled in
  from `outputs/metrics.json`, and a check confirms no number is typed by hand.
