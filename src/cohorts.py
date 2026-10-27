"""Section 4: export cohort triangles, retention curves and the headline repeat rates."""
from src import config


def curve(df, active_col, size_col):
    """Pooled curve: sum of active / sum of cohort size over observed cells only.

    Pooling only observed cells is the censoring fix: month 12 is averaged over
    the cohorts that have reached month 12, not over all cohorts.
    """
    obs = df[df.is_observed]
    g = obs.groupby("month_number").agg(active=(active_col, "sum"), base=(size_col, "sum"),
                                        n_cohorts=("cohort_month", "nunique")).reset_index()
    g["rate"] = g.active / g.base
    return g


def main(con):
    cust = con.execute("select * from mart_customer_cohorts").df()
    sell = con.execute("select * from mart_seller_cohorts").df()
    cust.to_csv(config.OUTPUTS / "cohort_customers_long.csv", index=False)
    sell.to_csv(config.OUTPUTS / "cohort_sellers_long.csv", index=False)

    # Wide triangles for reading by eye and for the dashboard heatmap.
    cust.pivot(index="cohort_month", columns="month_number", values="retention") \
        .to_csv(config.OUTPUTS / "cohort_customers_triangle.csv")
    sell.pivot(index="cohort_month", columns="month_number", values="activity_rate") \
        .to_csv(config.OUTPUTS / "cohort_sellers_triangle.csv")

    c_curve = curve(cust, "active_customers", "cohort_customers")
    s_curve = curve(sell, "active_sellers", "cohort_sellers")
    # Cumulative repeat curve uses the same pooling rule.
    obs = cust[cust.is_observed]
    cum = obs.groupby("month_number").agg(repeated=("repeated_by_month", "sum"),
                                          base=("cohort_customers", "sum")).reset_index()
    cum["rate"] = cum.repeated / cum.base
    c_curve["cumulative_repeat_rate"] = cum["rate"].values
    c_curve.to_csv(config.OUTPUTS / "retention_curve_customers.csv", index=False)
    s_curve.to_csv(config.OUTPUTS / "retention_curve_sellers.csv", index=False)

    one = lambda s: con.execute(s).fetchone()[0]
    rate_at = lambda g, k: float(g.loc[g.month_number == k, "rate"].iloc[0])
    m = {
        "customers": int(one("select count(*) from mart_customers")),
        "repeat_customers": int(one("select count(*) from mart_customers where is_repeat_customer")),
        # All-time rate: every customer, however recently acquired. A lower bound.
        "repeat_rate_all_time": float(one("select avg(is_repeat_customer::int) from mart_customers")),
        # Censoring-safe rate: only customers with the full window observed.
        "repeat_rate_180d": float(one(
            "select avg(repeat_in_window::int) from mart_customers where repeat_window_observed")),
        "repeat_rate_180d_base": int(one(
            "select count(*) from mart_customers where repeat_window_observed")),
        "cust_retention_m1": rate_at(c_curve, 1),
        "cust_retention_m3": rate_at(c_curve, 3),
        "cust_retention_m6": rate_at(c_curve, 6),
        "cust_retention_m12": rate_at(c_curve, 12),
        "cust_cum_repeat_m12": float(cum.loc[cum.month_number == 12, "rate"].iloc[0]),
        "cust_cum_repeat_m12_cohorts": int(c_curve.loc[c_curve.month_number == 12, "n_cohorts"].iloc[0]),
        "seller_activity_m1": rate_at(s_curve, 1),
        "seller_activity_m3": rate_at(s_curve, 3),
        "seller_activity_m6": rate_at(s_curve, 6),
        "seller_activity_m12": rate_at(s_curve, 12),
        "cohort_count": int(cust.cohort_month.nunique()),
        "cohort_first": str(cust.cohort_month.min())[:7],
        "cohort_last": str(cust.cohort_month.max())[:7],
        "median_days_to_first_repeat": float(one(
            "select median(days_to_first_repeat) from mart_customers where is_repeat_customer")),
    }
    return m
