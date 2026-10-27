"""Section 10: verification.

1. Rebuild funnel conversion, repeat rates and cohort retention independently in
   pandas, straight from the raw CSVs, and assert they match the SQL within 1e-6.
2. Check that every number quoted in README.md and docs/memo.md exists in
   outputs/metrics.json (or is a declared structural constant).
3. Check the writing rules (no em-dashes, no emojis) in README and memo.

Writes outputs/verification.json and prints a report. Returns True only if all pass.
"""
import json
import re

import numpy as np
import pandas as pd

from src import config
from src.report import FORMATS

TOL = 1e-6


# ------------------------------------------------------------ pandas rebuild
def load_raw():
    r = lambda k: pd.read_csv(config.RAW_DIR / config.RAW_FILES[k], dtype=str, keep_default_na=False,
                              na_values=[""])
    orders = r("raw_orders")
    for c in ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
              "order_delivered_customer_date"]:
        orders[c] = pd.to_datetime(orders[c])
    customers = r("raw_customers")
    reviews = r("raw_order_reviews")
    return orders, customers, reviews


def pandas_funnel(orders, reviews):
    o = orders.copy()
    o["delivered"] = (o.order_status == "delivered") & o.order_delivered_customer_date.notna()
    o["shipped"] = o.delivered | o.order_delivered_carrier_date.notna()
    o["approved"] = o.shipped | o.order_approved_at.notna()
    o["reviewed"] = o.delivered & o.order_id.isin(set(reviews.order_id))
    o["month"] = o.order_purchase_timestamp.dt.strftime("%Y-%m")

    def agg(g):
        n = len(g)
        return pd.Series({"n_purchased": n, "n_approved": g.approved.sum(), "n_shipped": g.shipped.sum(),
                          "n_delivered": g.delivered.sum(), "n_reviewed": g.reviewed.sum(),
                          "conv_purchased_to_delivered": g.delivered.sum() / n,
                          "conv_delivered_to_reviewed": g.reviewed.sum() / g.delivered.sum()
                          if g.delivered.sum() else np.nan})
    overall = agg(o).to_frame().T.assign(dimension_value="all")
    by_month = o.groupby("month").apply(agg, include_groups=False).reset_index().rename(
        columns={"month": "dimension_value"})
    return overall, by_month


def pandas_customers(orders, customers):
    o = orders[(orders.order_status == "delivered") & orders.order_delivered_customer_date.notna()]
    o = o.merge(customers[["customer_id", "customer_unique_id"]], on="customer_id")
    o = o.assign(pdate=o.order_purchase_timestamp.dt.normalize())
    # Data end uses status only, exactly like int_data_window.
    data_end = orders.loc[orders.order_status == "delivered", "order_purchase_timestamp"].max().normalize()
    last_day = data_end + pd.offsets.MonthEnd(0)
    last_complete = data_end.replace(day=1) if data_end == last_day else \
        (data_end.replace(day=1) - pd.offsets.MonthBegin(1))

    first = o.sort_values(["order_purchase_timestamp", "order_id"]).groupby("customer_unique_id").first()
    first_date = first.pdate
    dates = o.groupby("customer_unique_id").pdate
    n_days = dates.nunique()
    later = o.merge(first_date.rename("first_date"), left_on="customer_unique_id", right_index=True)
    later = later[later.pdate > later.first_date].groupby("customer_unique_id").pdate.min()
    cust = pd.DataFrame({"first_date": first_date, "n_days": n_days}).join(later.rename("next_date"))
    window = pd.Timedelta(days=config.REPEAT_WINDOW_DAYS)
    cust["observed"] = cust.first_date + window <= data_end
    cust["repeat_180"] = cust.next_date.notna() & (cust.next_date <= cust.first_date + window)
    rates = {
        "repeat_rate_all_time": float((cust.n_days > 1).mean()),
        "repeat_rate_180d": float(cust.loc[cust.observed, "repeat_180"].mean()),
    }

    # Cohort retention.
    act = o.assign(month=o.pdate.dt.to_period("M").dt.to_timestamp())[["customer_unique_id", "month"]] \
        .drop_duplicates()
    act["cohort"] = act.groupby("customer_unique_id").month.transform("min")
    act["k"] = (act.month.dt.year - act.cohort.dt.year) * 12 + (act.month.dt.month - act.cohort.dt.month)
    start = pd.Timestamp(config.COHORT_START)
    act = act[(act.cohort >= start) & (act.cohort <= last_complete)]
    size = act[act.k == 0].groupby("cohort").size().rename("size")
    cells = act.groupby(["cohort", "k"]).size().rename("active").reset_index().merge(size, on="cohort")
    cells = cells[cells.apply(lambda r: r.cohort + pd.DateOffset(months=int(r.k)) <= last_complete, axis=1)]
    cells["retention"] = cells.active / cells["size"]
    return rates, cells


def compare(name, a, b, results):
    diff = float(np.nanmax(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))) if len(a) else 0.0
    ok = diff <= TOL and len(a) == len(b)
    results.append({"check": name, "max_abs_diff": diff, "n": len(a), "passed": ok})


def rebuild_checks(con):
    orders, customers, reviews = load_raw()
    results = []

    overall, by_month = pandas_funnel(orders, reviews)
    sql = con.execute("select * from mart_fulfilment_funnel").df()
    s_ov = sql[sql.dimension == "overall"].iloc[0]
    for col in ["n_purchased", "n_approved", "n_shipped", "n_delivered", "n_reviewed",
                "conv_purchased_to_delivered", "conv_delivered_to_reviewed"]:
        compare(f"funnel overall {col}", [overall[col].iloc[0]], [s_ov[col]], results)
    s_m = sql[sql.dimension == "month"].set_index("dimension_value").sort_index()
    p_m = by_month.set_index("dimension_value").sort_index()
    for col in ["n_delivered", "n_reviewed", "conv_purchased_to_delivered"]:
        compare(f"funnel by month {col}", p_m[col].values, s_m.loc[p_m.index, col].values, results)

    rates, cells = pandas_customers(orders, customers)
    m = json.loads((config.OUTPUTS / "metrics.json").read_text())
    for k, v in rates.items():
        compare(f"customers {k}", [v], [m[k]], results)
        sql_v = con.execute({
            "repeat_rate_all_time": "select avg(is_repeat_customer::int) from mart_customers",
            "repeat_rate_180d": "select avg(repeat_in_window::int) from mart_customers where repeat_window_observed",
        }[k]).fetchone()[0]
        compare(f"customers {k} (SQL)", [v], [sql_v], results)

    sc = con.execute("select cohort_month, month_number, retention from mart_customer_cohorts "
                     "where is_observed").df()
    sc["cohort_month"] = pd.to_datetime(sc.cohort_month)
    # Cells with zero buyers exist in SQL (explicit zeros) but not in the pandas group-by.
    merged = sc.merge(cells, left_on=["cohort_month", "month_number"], right_on=["cohort", "k"], how="left")
    merged["retention_y"] = merged.retention_y.fillna(0.0)
    compare("cohort retention (all observed cells)", merged.retention_y.values, merged.retention_x.values, results)
    compare("cohort cell count (pandas cells found in SQL)",
            [len(cells)], [merged.cohort.notna().sum()], results)
    return results


# ----------------------------------------------------------- number checking
# Thousands separators only when followed by exactly three digits, so "day 1, then" yields "1".
NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
DATE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")

# Numbers allowed in prose that are definitions, not results. Each has a reason.
STRUCTURAL = {
    "0": "day 0 = delivered on the promised day",
    "1": "1-star, day 1",
    "2": "day 2 (labelled day on the curve)",
    "3": "day 3, '3 or more days late'",
    str(config.REPEAT_WINDOW_DAYS): "repeat window in days (config)",
    str(config.SELLER_ACTIVE_DAYS): "seller activity window in days (config)",
    str(round(100 * (1 - config.ALPHA))): "confidence level (config)",
    str(round(100 * config.EXPERIMENT_MDE_RELATIVE)): "experiment MDE in percent (config)",
    "2016": "year", "2017": "year", "2018": "year",
    "3.11": "Python version",
    "6": "exponent of the pandas vs SQL tolerance (1e-6, verify.TOL)",
    "4.0": "data licence version (CC BY-NC-SA 4.0)",
}


def strip_markdown(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)          # code blocks
    text = re.sub(r"`[^`]*`", " ", text)                        # inline code (file names)
    text = re.sub(r"\]\([^)]*\)", "]", text)                    # link targets
    text = re.sub(r"\[[^\]]*\.(md|html|py|sql|dax)\]", " ", text)  # link labels that are file names
    return text


def candidates(m):
    cands = set()
    for v in m.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            for f in FORMATS.values():
                try:
                    cands.update(NUM.findall(f(v)))
                except (ValueError, TypeError):
                    pass
        elif isinstance(v, str):
            cands.update(NUM.findall(v))
            cands.update(DATE.findall(v))
    return cands


def untraced_numbers(markdown, cands):
    """Numbers (and dates) in a markdown text that are neither metrics nor structural constants."""
    text = strip_markdown(markdown)
    dates = DATE.findall(text)
    nums = NUM.findall(DATE.sub(" ", text))
    unknown = sorted({n for n in nums if n not in cands and n not in STRUCTURAL})
    return unknown + [d for d in dates if d not in cands], len(nums) + len(dates)


def number_checks():
    m = json.loads((config.OUTPUTS / "metrics.json").read_text())
    cands = candidates(m)
    results = []
    for path in [config.ROOT / "README.md", config.DOCS / "memo.md", config.DOCS / "INTERVIEW_PREP.md"]:
        unknown, n = untraced_numbers(path.read_text(encoding="utf-8"), cands)
        results.append({"check": f"numbers in {path.name} traced to outputs/metrics.json",
                        "n": n, "unknown": unknown, "passed": not unknown})
        raw = path.read_text(encoding="utf-8")
        emoji = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", raw)
        results.append({"check": f"style in {path.name} (no em-dash, no emoji)",
                        "n": raw.count("—") + len(emoji), "passed": "—" not in raw and not emoji})
    return results


def main(con):
    results = rebuild_checks(con) + number_checks()
    (config.OUTPUTS / "verification.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    for r in results:
        extra = f"  unknown={r['unknown']}" if r.get("unknown") else ""
        diff = f"  max_abs_diff={r['max_abs_diff']:.2e}" if "max_abs_diff" in r else ""
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['check']} (n={r['n']}){diff}{extra}")
    return all(r["passed"] for r in results)
