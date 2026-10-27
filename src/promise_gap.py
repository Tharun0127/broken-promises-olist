"""Section 5: the promise gap. Descriptive curve, then the regression discontinuity."""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src import config, rd

OUTCOMES = {
    # name: (column, sample description)
    "one_star": ("one_star", "delivered orders with a review"),
    "review_score": ("review_score", "delivered orders with a review"),
    "repeat_180": ("repeat_180", "first orders with a full 180-day window"),
}
PRIMARY = "one_star"


def load(con):
    return con.execute("select * from mart_promise_gap").df()


def descriptive_curve(df):
    lo, hi = config.RD_DESCRIPTIVE_RANGE
    d = df[(df.days_late >= lo) & (df.days_late <= hi)]
    rows = []
    for name, (col, _) in OUTCOMES.items():
        g = d.dropna(subset=[col]).groupby("days_late")[col].agg(["mean", "std", "size"]).reset_index()
        g["se"] = g["std"] / np.sqrt(g["size"])
        g["ci_low"], g["ci_high"] = g["mean"] - 1.96 * g.se, g["mean"] + 1.96 * g.se
        g["outcome"] = name
        rows.append(g.rename(columns={"size": "n"}))
    t = d.groupby("days_late").review_before_delivery.agg(["mean", "size"]).reset_index()
    t["outcome"] = "review_before_delivery"
    rows.append(t.rename(columns={"size": "n"}))
    return pd.concat(rows, ignore_index=True)


def naive_gaps(df):
    """Simple late vs on-time comparison over ALL orders. Not causal."""
    out = {}
    for name, (col, _) in OUTCOMES.items():
        s = df.dropna(subset=[col])
        on, late = s.loc[~s.is_late, col].mean(), s.loc[s.is_late, col].mean()
        out[name] = {"on_time": on, "late": late, "diff": late - on}
    return out


def balance_covariates(df):
    """Pre-delivery covariates, plus dummies for the biggest states and categories."""
    b = df.copy()
    b["log_items_value"] = np.log1p(b.items_value)
    b["log_freight"] = np.log1p(b.freight_value)
    covs = ["log_items_value", "log_freight", "n_items", "promised_days"]
    for s in b.customer_state.value_counts().index[:5]:
        b[f"state_{s}"] = (b.customer_state == s).astype(float)
        covs.append(f"state_{s}")
    for cat in b.category_en.value_counts().index[:5]:
        b[f"cat_{cat}"] = (b.category_en == cat).astype(float)
        covs.append(f"cat_{cat}")
    return b, covs


def predicted_outcome(b):
    """One-number balance check: predict 1-star from covariates only (never from
    days late), then test the prediction for a jump at the cutoff."""
    s = b.dropna(subset=["one_star"]).copy()
    s["month"] = s.purchase_month.astype(str)
    model = smf.ols("one_star ~ np.log1p(items_value) + np.log1p(freight_value) + n_items"
                    " + promised_days + C(customer_state) + C(category_en) + C(month)", data=s).fit()
    b["predicted_one_star"] = model.predict(b.assign(month=b.purchase_month.astype(str)))
    return b


def run(df, h=None):
    x = df.days_late.values
    results, extras = [], {}

    # 1. Bandwidth by cross-validation on the primary outcome.
    if h is None:
        h, cv = rd.cv_bandwidth(x, df[PRIMARY].values)
        extras["cv"] = cv
    bandwidths = sorted({max(2, round(h / 2)), h, 2 * h})

    # 2. Main estimates, robustness across bandwidths, and the donut.
    for name, (col, _) in OUTCOMES.items():
        y = df[col].values
        for bw in bandwidths:
            r = rd.local_linear_rd(x, y, h=bw)
            results.append({"outcome": name, "spec": "main" if bw == h else "bandwidth", **r})
        r = rd.local_linear_rd(x, y, h=h, kernel="uniform")
        results.append({"outcome": name, "spec": "uniform_kernel", **r})
        r = rd.local_linear_rd(x, y, h=h, exclude=[0, 1])
        results.append({"outcome": name, "spec": "donut_0_1", **r})
        r = rd.adjacent_days(x, y)
        results.append({"outcome": name, "spec": "adjacent_days", **r})
        for p in rd.placebo_cutoffs(x, y, h):
            results.append({"outcome": name, "spec": f"placebo_{p.pop('placebo')}", **p})

    # 3. Selection check: does the chance of leaving a review jump?
    r = rd.local_linear_rd(x, df.has_review.astype(float).values, h=h)
    results.append({"outcome": "has_review", "spec": "main", **r})

    # 4. Survey timing check (descriptive only: conditioning on a post-treatment variable).
    after = df[df.review_before_delivery == False]  # noqa: E712  (NaN must be excluded)
    r = rd.local_linear_rd(after.days_late.values, after.one_star.values, h=h)
    results.append({"outcome": "one_star", "spec": "reviews_after_delivery_only", **r})

    res = pd.DataFrame(results)

    # 5. Density at the cutoff.
    dens = rd.density_test(x, h=h)

    # 6. Covariate balance.
    b, covs = balance_covariates(df)
    b = predicted_outcome(b)
    bal = []
    for cv_name in covs + ["predicted_one_star"]:
        r = rd.local_linear_rd(x, b[cv_name].values, h=h)
        bal.append({"covariate": cv_name, **r})
    bal = pd.DataFrame(bal)
    return h, bandwidths, res, dens, bal, extras


def main(con):
    df = load(con)
    curve = descriptive_curve(df)
    h, bws, res, dens, bal, extras = run(df)

    curve.to_csv(config.OUTPUTS / "rd_descriptive_curve.csv", index=False)
    res.to_csv(config.OUTPUTS / "rd_results.csv", index=False)
    bal.to_csv(config.OUTPUTS / "rd_balance.csv", index=False)
    pd.DataFrame([dens]).to_csv(config.OUTPUTS / "rd_density.csv", index=False)
    extras["cv"].to_csv(config.OUTPUTS / "rd_bandwidth_cv.csv", index=False)
    counts = df.days_late.value_counts().sort_index().rename_axis("days_late").reset_index(name="orders")
    counts.to_csv(config.OUTPUTS / "rd_order_counts_by_day.csv", index=False)

    get = lambda o, s, bw=h: res[(res.outcome == o) & (res.spec == s) & (res.h == bw)].iloc[0]
    naive = naive_gaps(df)
    m = {"rd_bandwidth": h, "rd_bandwidth_low": bws[0], "rd_bandwidth_high": bws[-1],
         "late_rate": float(df.is_late.mean()),
         "late_orders": int(df.is_late.sum()),
         "late_review_before_delivery": float(df.loc[df.is_late, "review_before_delivery"].mean()),
         "ontime_review_before_delivery": float(df.loc[~df.is_late, "review_before_delivery"].mean())}
    for o in OUTCOMES:
        main_r = get(o, "main")
        for k in ["estimate", "ci_low", "ci_high", "p_value", "control_mean_at_cutoff", "n_left", "n_right"]:
            m[f"rd_{o}_{k}"] = float(main_r[k])
        for bw in bws:
            m[f"rd_{o}_h{bw}_estimate"] = float(get(o, "main" if bw == h else "bandwidth", bw).estimate)
        adj = get(o, "adjacent_days", 1)
        m[f"rd_{o}_adjacent_estimate"] = float(adj.estimate)
        m[f"rd_{o}_adjacent_ci_low"] = float(adj.ci_low)
        m[f"rd_{o}_adjacent_ci_high"] = float(adj.ci_high)
        m[f"rd_{o}_adjacent_p_value"] = float(adj.p_value)
        m[f"rd_{o}_day0_mean"] = float(adj.control_mean_at_cutoff)
        m[f"rd_{o}_day1_mean"] = float(adj.control_mean_at_cutoff + adj.estimate)
        m[f"rd_{o}_donut_estimate"] = float(get(o, "donut_0_1").estimate)
        m[f"rd_{o}_donut_ci_low"] = float(get(o, "donut_0_1").ci_low)
        m[f"rd_{o}_donut_ci_high"] = float(get(o, "donut_0_1").ci_high)
        for side in ["below", "above"]:
            m[f"rd_{o}_placebo_{side}_estimate"] = float(get(o, f"placebo_{side}").estimate)
            m[f"rd_{o}_placebo_{side}_p"] = float(get(o, f"placebo_{side}").p_value)
        m[f"naive_{o}_on_time"] = float(naive[o]["on_time"])
        m[f"naive_{o}_late"] = float(naive[o]["late"])
        m[f"naive_{o}_diff"] = float(naive[o]["diff"])
    oc = curve[curve.outcome == "one_star"].set_index("days_late")["mean"]
    rb = curve[curve.outcome == "review_before_delivery"].set_index("days_late")["mean"]
    for dl in [2, 3, 6]:
        m[f"one_star_day{dl}"] = float(oc[dl])
        m[f"review_before_delivery_day{dl}"] = float(rb[dl])
    m["one_star_late_6plus"] = float(df.loc[df.days_late >= 6, "one_star"].mean())
    m["rd_one_star_relative_jump"] = m["rd_one_star_estimate"] / m["rd_one_star_control_mean_at_cutoff"]
    hr = get("has_review", "main")
    m["rd_has_review_estimate"], m["rd_has_review_p_value"] = float(hr.estimate), float(hr.p_value)
    ad = get("one_star", "reviews_after_delivery_only")
    m["rd_one_star_after_delivery_estimate"] = float(ad.estimate)
    m["rd_one_star_after_delivery_ci_low"] = float(ad.ci_low)
    m["rd_one_star_after_delivery_ci_high"] = float(ad.ci_high)
    m["rd_one_star_after_delivery_n_right"] = int(ad.n_right)
    m.update({f"density_{k}": float(v) for k, v in dens.items()})
    m["balance_n_tested"] = int(len(bal) - 1)
    m["balance_n_significant"] = int((bal.iloc[:-1].p_value < config.ALPHA).sum())
    pred = bal[bal.covariate == "predicted_one_star"].iloc[0]
    m["balance_predicted_estimate"] = float(pred.estimate)
    m["balance_predicted_p_value"] = float(pred.p_value)
    m["balance_predicted_ci_low"] = float(pred.ci_low)
    m["balance_predicted_ci_high"] = float(pred.ci_high)
    from src.rd_report import write_doc
    write_doc(m)
    return m
