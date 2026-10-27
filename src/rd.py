"""Regression discontinuity tools for a discrete running variable.

Notation used throughout:
    x  = days late (integer). x <= 0 is on time, x >= 1 is late.
    c  = first treated value (1 for the real cutoff).
    h  = bandwidth in days per side: left uses x in [c-h, c-1], right uses [c, c+h-1].
    xc = x - (c - 0.5): the running variable centered halfway between the last
         untreated day and the first treated day. The jump is measured at xc = 0.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from src import config


def window(x, c, h):
    return (x >= c - h) & (x <= c + h - 1)


def kernel_weights(xc, h, kernel="triangular"):
    if kernel == "uniform":
        return np.ones_like(xc, dtype=float)
    # Triangular: weight falls linearly to zero at distance h from the cutoff.
    return np.clip(1 - np.abs(xc) / h, 0, None)


def local_linear_rd(x, y, c=config.RD_FIRST_LATE_DAY, h=7, kernel="triangular",
                    exclude=None, alpha=config.ALPHA):
    """Jump in E[y | x] at the cutoff from a local linear fit on each side.

    Model: y = a + tau*D + b*xc + g*D*xc, with D = 1 if x >= c.
    tau is the discontinuity. Separate slopes per side, so neither side's
    trend leaks into the other. HC1 robust standard errors.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    keep = window(x, c, h) & ~np.isnan(y)
    if exclude is not None:                      # donut: drop days at the line
        keep &= ~np.isin(x, exclude)
    x, y = x[keep], y[keep]
    d = (x >= c).astype(float)
    xc = x - (c - 0.5)
    w = kernel_weights(xc, h, kernel)
    X = np.column_stack([np.ones_like(xc), d, xc, d * xc])
    fit = sm.WLS(y, X, weights=w).fit(cov_type="HC1")
    tau, se = fit.params[1], fit.bse[1]
    z = stats.norm.ppf(1 - alpha / 2)
    return {
        "estimate": tau, "se": se, "ci_low": tau - z * se, "ci_high": tau + z * se,
        "p_value": 2 * (1 - stats.norm.cdf(abs(tau / se))) if se > 0 else np.nan,
        "control_mean_at_cutoff": fit.params[0],          # left-side line at the cutoff
        "n_left": int((d == 0).sum()), "n_right": int((d == 1).sum()), "h": h, "c": c,
    }


def adjacent_days(x, y, c=config.RD_FIRST_LATE_DAY, alpha=config.ALPHA):
    """Local randomisation view: compare the first late day with the last on-time day.

    Assumes orders one day either side of the promise are comparable and that the
    trend within one day is negligible. No slope is fitted, so a steep trend on
    one side shows up as part of the difference.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    a, b = y[(x == c) & ~np.isnan(y)], y[(x == c - 1) & ~np.isnan(y)]
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    z = stats.norm.ppf(1 - alpha / 2)
    return {"estimate": diff, "se": se, "ci_low": diff - z * se, "ci_high": diff + z * se,
            "p_value": 2 * (1 - stats.norm.cdf(abs(diff / se))),
            "control_mean_at_cutoff": b.mean(), "n_left": len(b), "n_right": len(a), "h": 1, "c": c}


def cell_means(x, y):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    return df.groupby("x").y.agg(["mean", "size"]).rename(columns={"size": "n"}).reset_index()


def cv_bandwidth(x, y, grid=config.RD_BANDWIDTH_GRID, c=config.RD_FIRST_LATE_DAY,
                 eval_days=config.RD_CV_WINDOW):
    """Leave-one-out cross-validation for the bandwidth (Ludwig and Miller style).

    For each day x0 near the cutoff, predict its mean outcome from a straight
    line fitted only on the h days further from the cutoff on the same side.
    This mimics the RD task: predicting a boundary value from one side.
    Score = order-weighted mean squared prediction error. Working on daily
    means is equivalent to working on orders, because within-day noise does not
    depend on h.
    """
    cells = cell_means(x, y).set_index("x")
    rows = []
    for h in grid:
        sq_err, weight = 0.0, 0.0
        for x0 in range(c - eval_days, c + eval_days):
            if x0 not in cells.index:
                continue
            if x0 < c:      # left side: use days further left
                train = cells.loc[(cells.index >= x0 - h) & (cells.index <= x0 - 1)]
            else:           # right side: use days further right
                train = cells.loc[(cells.index >= x0 + 1) & (cells.index <= x0 + h)]
            if len(train) < 2:
                continue
            coef = np.polyfit(train.index.values, train["mean"].values, 1, w=np.sqrt(train["n"].values))
            pred = np.polyval(coef, x0)
            n0 = cells.loc[x0, "n"]
            sq_err += n0 * (cells.loc[x0, "mean"] - pred) ** 2
            weight += n0
        rows.append({"h": h, "cv_mse": sq_err / weight})
    table = pd.DataFrame(rows)
    best = int(table.loc[table.cv_mse.idxmin(), "h"])
    return best, table


def density_test(x, c=config.RD_FIRST_LATE_DAY, h=7):
    """Is there a jump in the NUMBER of orders at the cutoff?

    Poisson regression of daily order counts on the same RD design. exp(tau)
    is the ratio of counts just right vs just left of the cutoff. Quasi-Poisson
    scale (Pearson chi2) allows for overdispersion.
    """
    counts = pd.Series(np.asarray(x)).value_counts().sort_index()
    cells = counts[(counts.index >= c - h) & (counts.index <= c + h - 1)]
    xv = cells.index.values.astype(float)
    d = (xv >= c).astype(float)
    xc = xv - (c - 0.5)
    X = np.column_stack([np.ones_like(xc), d, xc, d * xc])
    fit = sm.GLM(cells.values, X, family=sm.families.Poisson()).fit(scale="X2")
    tau, se = fit.params[1], fit.bse[1]
    z = stats.norm.ppf(1 - config.ALPHA / 2)
    return {
        "log_jump": tau, "se": se, "count_ratio": np.exp(tau),
        "ratio_ci_low": np.exp(tau - z * se), "ratio_ci_high": np.exp(tau + z * se),
        "p_value": 2 * (1 - stats.norm.cdf(abs(tau / se))), "h": h,
        "count_day_0": int(counts.get(c - 1, 0)), "count_day_1": int(counts.get(c, 0)),
    }


def placebo_cutoffs(x, y, h, c=config.RD_FIRST_LATE_DAY):
    """Fake cutoffs one bandwidth below and above the real one.

    Each placebo window stays entirely on one side of the real cutoff, so the
    real jump cannot leak in. A good design shows no jump at either.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    out = []
    for label, pc, side in [("below", c - h, x < c), ("above", c + h, x >= c)]:
        r = local_linear_rd(x[side], y[side], c=pc, h=h)
        r["placebo"] = label
        out.append(r)
    return out
