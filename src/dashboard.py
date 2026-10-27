"""Section 8b: static interactive dashboard (docs/index.html) for GitHub Pages.

Four pages: Funnel, Cohorts, Promise Gap, Experiment Plan. Every chart title is
built from the numbers so it states the takeaway, and changes if the data does.
"""
import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs_version

from src import config

# Palette validated with the dataviz validator (light and dark steps).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SEQ_BLUE = [[0, "#e9f1fc"], [0.25, "#9ec5f4"], [0.5, "#5598e7"], [0.75, "#256abf"], [1, "#0d366b"]]

O = config.OUTPUTS


def pct(v, d=1):
    return f"{100 * v:.{d}f}%"


def base_layout(fig, title, height=380, xtitle=None, ytitle=None):
    fig.update_layout(
        title={"text": title, "x": 0, "xanchor": "left", "font": {"size": 16}},
        height=height, margin={"l": 60, "r": 20, "t": 60, "b": 50},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, sans-serif", "size": 13},
        hoverlabel={"font": {"size": 13}}, showlegend=False, bargap=0.25,
    )
    fig.update_xaxes(title=xtitle, showgrid=False, zeroline=False, ticks="outside", ticklen=4)
    fig.update_yaxes(title=ytitle, showgrid=True, gridwidth=1, zeroline=False)
    return fig


def div(fig, div_id):
    return pio.to_html(fig, full_html=False, include_plotlyjs=False, div_id=div_id,
                       config={"displayModeBar": False, "responsive": True})


def table_html(df):
    return df.to_html(index=False, classes="data", border=0, na_rep="")


# ---------------------------------------------------------------- Funnel page
def funnel_page(m):
    f = pd.read_csv(O / "funnel_fulfilment.csv")
    s = pd.read_csv(O / "funnel_seller.csv")
    ov = f[f.dimension == "overall"].iloc[0]
    stages = ["Purchased", "Approved", "Shipped", "Delivered", "Reviewed"]
    counts = [ov.n_purchased, ov.n_approved, ov.n_shipped, ov.n_delivered, ov.n_reviewed]
    fig1 = go.Figure(go.Bar(
        y=stages, x=counts, orientation="h", marker={"color": BLUE, "cornerradius": 4},
        text=[f"{c:,.0f} ({pct(c / counts[0])})" for c in counts], textposition="auto",
        hovertemplate="%{y}: %{x:,} orders<extra></extra>"))
    fig1.update_yaxes(autorange="reversed", showgrid=False)
    base_layout(fig1, f"{pct(m['funnel_conv_purchased_to_delivered'])} of orders reach the customer, and "
                      f"{pct(m['funnel_conv_delivered_to_reviewed'])} of those are reviewed",
                xtitle="Orders")

    mo = f[(f.dimension == "month") & (f.dimension_value >= "2017-01") & (f.dimension_value <= "2018-08")]
    peak = mo.loc[mo.median_h_ship_to_deliver.idxmax()]
    last = mo.iloc[-1]
    fig2 = go.Figure(go.Scatter(
        x=mo.dimension_value, y=mo.median_h_ship_to_deliver / 24, mode="lines+markers",
        line={"color": BLUE, "width": 2}, marker={"size": 8},
        hovertemplate="%{x}: %{y:.1f} days<extra></extra>"))
    base_layout(fig2, f"Median carrier time peaked at {peak.median_h_ship_to_deliver / 24:.1f} days "
                      f"({peak.dimension_value}) and fell to {last.median_h_ship_to_deliver / 24:.1f} by {last.dimension_value}",
                ytitle="Days from shipped to delivered (median)")

    so = s[s.dimension == "overall"].iloc[0]
    sstages = ["Leads", "Closed deal", "First sale", "Still selling at 90 days"]
    svals = [so.n_leads, so.n_closed, so.n_first_sale, so.n_still_selling]
    fig3 = go.Figure(go.Bar(
        x=sstages, y=svals, marker={"color": BLUE, "cornerradius": 4},
        text=[f"{v:,.0f}" for v in svals], textposition="outside",
        hovertemplate="%{x}: %{y:,}<extra></extra>"))
    base_layout(fig3, f"{pct(m['seller_conv_lead_to_closed'])} of leads close, and only "
                      f"{pct(m['seller_conv_closed_to_first_sale'])} of closed sellers ever make a sale",
                ytitle="Sellers")
    note3 = (f"The last stage counts only the {m['seller_first_sale_observed']:,.0f} sellers whose 90-day window is "
             f"fully observed; {m['seller_censored']:,.0f} are censored. Of those observed, "
             f"{pct(m['seller_conv_first_sale_to_still_selling'])} still sell.")

    org = s[(s.dimension == "lead_origin") & (s.n_closed >= 20)].sort_values("conv_closed_to_first_sale")
    best, worst = org.iloc[-1], org.iloc[0]
    fig4 = go.Figure(go.Bar(
        y=org.dimension_value, x=org.conv_closed_to_first_sale, orientation="h",
        marker={"color": BLUE, "cornerradius": 4}, text=[pct(v) for v in org.conv_closed_to_first_sale],
        textposition="auto", customdata=org.n_closed,
        hovertemplate="%{y}: %{x:.1%} of %{customdata} closed deals made a sale<extra></extra>"))
    fig4.update_xaxes(tickformat=".0%")
    base_layout(fig4, f"Closed deals from {best.dimension_value} sell most often ({pct(best.conv_closed_to_first_sale)}); "
                      f"{worst.dimension_value} least ({pct(worst.conv_closed_to_first_sale)})",
                xtitle="Closed deals that made a first sale (origins with 20+ deals)")

    tiles = [("Orders", f"{m['funnel_orders']:,.0f}"), ("Delivered", pct(m["funnel_conv_purchased_to_delivered"])),
             ("Median carrier time", f"{m['funnel_median_h_ship_to_deliver'] / 24:.1f} days"),
             ("Leads that close", pct(m["seller_conv_lead_to_closed"]))]
    body = (chart(fig1, "f1") + chart(fig2, "f2") + chart(fig3, "f3", note3) + chart(fig4, "f4"))
    return tiles, body


# ---------------------------------------------------------------- Cohort page
def cohort_page(m):
    c = pd.read_csv(O / "cohort_customers_long.csv", parse_dates=["cohort_month"])
    tri = c[c.month_number >= 1].pivot(index="cohort_month", columns="month_number", values="retention")
    tri.index = tri.index.strftime("%Y-%m")
    zmax = np.nanmax(tri.values)
    fig1 = go.Figure(go.Heatmap(
        z=tri.values, x=[str(k) for k in tri.columns], y=tri.index, colorscale=SEQ_BLUE,
        zmin=0, zmax=zmax, xgap=2, ygap=2, colorbar={"tickformat": ".1%", "thickness": 12},
        hovertemplate="Cohort %{y}, month %{x}: %{z:.2%} bought<extra></extra>"))
    fig1.update_yaxes(autorange="reversed", showgrid=False)
    base_layout(fig1, f"No cohort gets more than {pct(zmax)} of its customers back in any later month",
                height=520, xtitle="Months since first purchase", ytitle="First purchase month")

    rc = pd.read_csv(O / "retention_curve_customers.csv")
    fig2 = go.Figure(go.Scatter(
        x=rc.month_number, y=rc.cumulative_repeat_rate, mode="lines+markers",
        line={"color": BLUE, "width": 2}, marker={"size": 8}, customdata=rc.n_cohorts,
        hovertemplate="Month %{x}: %{y:.2%} have bought again (%{customdata} cohorts)<extra></extra>"))
    fig2.update_yaxes(tickformat=".1%", rangemode="tozero")
    base_layout(fig2, f"By month 12 only {pct(m['cust_cum_repeat_m12'])} of a cohort has bought again",
                xtitle="Months since first purchase", ytitle="Share of cohort with a repeat purchase")

    sc = pd.read_csv(O / "retention_curve_sellers.csv")
    sc = sc[sc.month_number >= 1]
    fig3 = go.Figure(go.Scatter(
        x=sc.month_number, y=sc.rate, mode="lines+markers", line={"color": ORANGE, "width": 2},
        marker={"size": 8}, hovertemplate="Month %{x}: %{y:.1%} of sellers made a sale<extra></extra>"))
    fig3.update_yaxes(tickformat=".0%", rangemode="tozero")
    base_layout(fig3, f"{pct(m['seller_activity_m1'], 0)} of sellers sell again the next month; "
                      f"{pct(m['seller_activity_m12'], 0)} still sell a year later",
                xtitle="Months since first sale", ytitle="Sellers active in the month")

    note = ("Each curve point pools only cohorts that have reached that month, so late cohorts with "
            "little history do not pull the curve down (right censoring). Blank cells in the triangle are "
            "months the data cannot see yet.")
    tiles = [("Repeat rate, all time", pct(m["repeat_rate_all_time"])),
             ("Repeat within 180 days", pct(m["repeat_rate_180d"])),
             ("Customers", f"{m['customers']:,.0f}"),
             ("Median days to repeat", f"{m['median_days_to_first_repeat']:.0f}")]
    return tiles, chart(fig1, "c1", note) + chart(fig2, "c2") + chart(fig3, "c3")


# ---------------------------------------------------------- Promise gap page
def promise_page(m):
    cur = pd.read_csv(O / "rd_descriptive_curve.csv")
    res = pd.read_csv(O / "rd_results.csv")
    h = int(m["rd_bandwidth"])
    rng = (-15, 15)

    def outcome_fig(name, title, ytitle, fmt, fit=True):
        d = cur[(cur.outcome == name) & cur.days_late.between(*rng)]
        fig = go.Figure()
        for side, color, label in [(d.days_late <= 0, BLUE, "On time"), (d.days_late >= 1, ORANGE, "Late")]:
            dd = d[side]
            err = None
            if "ci_high" in dd and dd.ci_high.notna().any():
                err = {"type": "data", "array": dd.ci_high - dd["mean"], "arrayminus": dd["mean"] - dd.ci_low,
                       "thickness": 1.5, "width": 0, "color": color}
            fig.add_trace(go.Scatter(
                x=dd.days_late, y=dd["mean"], mode="markers", name=label, error_y=err,
                marker={"size": 9, "color": color, "line": {"width": 2, "color": "rgba(252,252,251,1)"}},
                customdata=dd.n, hovertemplate=f"Day %{{x}}: %{{y:{fmt}}} (n=%{{customdata:,}})<extra>{label}</extra>"))
        if fit:   # local linear fits used by the RD, each side within the bandwidth
            for lo, hi, color in [(1 - h, 0, BLUE), (1, h, ORANGE)]:
                dd = d[d.days_late.between(lo, hi)]
                w = np.clip(1 - np.abs(dd.days_late - 0.5) / h, 0, None) * dd.n
                coef = np.polyfit(dd.days_late, dd["mean"], 1, w=np.sqrt(w))
                # Draw each fit from its outer edge to the cutoff at 0.5.
                xs = np.array([lo, 0.5]) if hi <= 0 else np.array([0.5, hi])
                fig.add_trace(go.Scatter(x=xs, y=np.polyval(coef, xs), mode="lines", hoverinfo="skip",
                                         line={"color": color, "width": 2, "dash": "dot"}))
        fig.add_vline(x=0.5, line={"width": 1, "dash": "dash", "color": "#8a8985"})
        fig.add_annotation(x=0.5, y=1.02, yref="paper", text="promise date", showarrow=False,
                           font={"size": 12}, xanchor="left")
        fig.update_yaxes(tickformat=fmt.replace("%", "") if "%" not in fmt else ".0%")
        return base_layout(fig, title, xtitle="Days delivered after the estimated date", ytitle=ytitle)

    fig1 = outcome_fig("one_star", f"1-star reviews climb from {pct(m['rd_one_star_day0_mean'])} on the promise day to "
                                   f"{pct(m['one_star_day3'])} three days late", "1-star rate", ".1%")
    fig2 = outcome_fig("review_before_delivery",
                       f"From day 3, {pct(m['review_before_delivery_day3'], 0)} of late customers are surveyed "
                       f"before the parcel arrives", "Reviews sent before delivery", ".0%", fit=False)
    fig4 = outcome_fig("repeat_180", f"Repeat purchase shows no clear change at the promise date "
                                     f"(RD {100 * m['rd_repeat_180_estimate']:+.1f} pp, CI includes zero)",
                       "Repeat within 180 days (first orders)", ".1%")

    labels = {"main": f"Local linear, h={h} (main)", "bandwidth": "Local linear, h={h}",
              "uniform_kernel": "Uniform kernel", "donut_0_1": "Donut (drop days 0 and 1)",
              "adjacent_days": "Day 1 vs day 0", "placebo_below": "Placebo cutoff below",
              "placebo_above": "Placebo cutoff above", "reviews_after_delivery_only": "Reviews after delivery only"}
    r = res[res.outcome == "one_star"].copy()
    r["label"] = [labels[s].format(h=hh) if s != "main" else labels[s] for s, hh in zip(r.spec, r.h)]
    r = r.iloc[::-1]
    sig = r.p_value < config.ALPHA
    fig3 = go.Figure(go.Scatter(
        x=r.estimate, y=r.label, mode="markers",
        error_x={"type": "data", "array": r.ci_high - r.estimate, "arrayminus": r.estimate - r.ci_low,
                 "thickness": 2, "width": 0, "color": BLUE},
        marker={"size": 10, "color": np.where(sig, ORANGE, BLUE), "line": {"width": 2, "color": "rgba(252,252,251,1)"}},
        customdata=np.column_stack([r.ci_low, r.ci_high, r.p_value]),
        hovertemplate="%{y}: %{x:+.1%} (95% CI %{customdata[0]:+.1%} to %{customdata[1]:+.1%}, "
                      "p=%{customdata[2]:.3f})<extra></extra>"))
    fig3.add_vline(x=0, line={"width": 1, "color": "#8a8985"})
    fig3.update_xaxes(tickformat="+.0%")
    base_layout(fig3, f"Allowing for the trend there is no sharp jump ({100 * m['rd_one_star_estimate']:+.1f} pp); "
                      f"day 1 vs day 0 shows {100 * m['rd_one_star_adjacent_estimate']:+.1f} pp",
                height=420, xtitle="Change in 1-star rate at the promise date (orange = significant at 5%)")
    fig3.update_layout(margin={"l": 230})

    cnt = pd.read_csv(O / "rd_order_counts_by_day.csv")
    cnt = cnt[cnt.days_late.between(*rng)]
    fig5 = go.Figure(go.Bar(
        x=cnt.days_late, y=cnt.orders, marker={"color": np.where(cnt.days_late >= 1, ORANGE, BLUE), "cornerradius": 4},
        hovertemplate="Day %{x}: %{y:,} orders<extra></extra>"))
    fig5.add_vline(x=0.5, line={"width": 1, "dash": "dash", "color": "#8a8985"})
    base_layout(fig5, f"Orders bunch on the right side of the line: {m['density_count_day_0']:,.0f} arrive on day 0, "
                      f"{m['density_count_day_1']:,.0f} on day 1", xtitle="Days delivered after the estimated date",
                ytitle="Delivered orders")
    note5 = (f"The density test fails (count ratio {m['density_count_ratio']:.2f}, p {m['density_p_value']:.4f}). "
             "Carriers likely push to meet the date, so orders just on time may differ from orders just late. "
             f"{m['balance_n_significant']} of {m['balance_n_tested']} covariates also jump at the line.")

    note1 = ("Dots: daily rate with 95% CI. Dotted lines: the local linear fits the RD uses. "
             "This is a local effect at the promise date, not the effect of being a week late.")
    tiles = [("Late deliveries", pct(m["late_rate"])),
             ("1-star: on time vs late", f"{pct(m['naive_one_star_on_time'])} vs {pct(m['naive_one_star_late'])}"),
             ("RD jump in 1-star", f"{100 * m['rd_one_star_estimate']:+.1f} pp"),
             ("Day 1 vs day 0", f"{100 * m['rd_one_star_adjacent_estimate']:+.1f} pp")]
    body = (chart(fig1, "p1", note1) + chart(fig2, "p2") + chart(fig3, "p3") + chart(fig4, "p4")
            + chart(fig5, "p5", note5))
    return tiles, body


# ----------------------------------------------------------- Experiment page
def experiment_page(m):
    pw = pd.read_csv(O / "experiment_power.csv")
    fig1 = go.Figure(go.Scatter(
        x=pw.relative_drop_in_one_star, y=pw.months_at_measured_volume, mode="lines+markers+text",
        line={"color": BLUE, "width": 2}, marker={"size": 9},
        text=[f"{v:,.0f}/arm" for v in pw.n_per_arm], textposition="top right",
        hovertemplate="MDE %{x:.0%}: %{y:.1f} months<extra></extra>"))
    fig1.update_xaxes(tickformat=".0%")
    base_layout(fig1, f"Detecting a {pct(m['exp_mde_relative'], 0)} drop in 1-star reviews needs "
                      f"{m['exp_n_per_arm']:,.0f} orders per arm, about {m['exp_months']:.1f} months",
                xtitle="Relative drop in the 1-star rate to detect", ytitle="Months of late orders needed")

    sz = pd.read_csv(O / "sizing.csv")
    sz = sz[sz.scope == "all_late"]
    names = {"low": "Low (favourable CI bound)", "base": "Base (point estimate)", "high": "High (harmful CI bound)",
             "naive_reference": "Naive gap (not causal)"}
    fig2 = go.Figure(go.Bar(
        x=[names[s] for s in sz.scenario], y=sz.loss_per_quarter,
        marker={"color": np.where(sz.loss_per_quarter > 0, ORANGE, BLUE), "cornerradius": 4},
        text=[f"R$ {v:,.0f}" for v in sz.loss_per_quarter], textposition="outside",
        hovertemplate="%{x}: R$ %{y:,.0f} per quarter<extra></extra>"))
    base_layout(fig2, f"Even the high scenario puts only R$ {m['size_loss_high_all_late']:,.0f} of repeat order value "
                      f"at risk per quarter", ytitle="Repeat order value lost per quarter (R$)")

    design = f"""
<div class="card prose">
<p><strong>This is a design, not a run experiment.</strong></p>
<ul>
<li><strong>Hypothesis:</strong> a proactive message with a revised date, sent the day after a missed promise,
changes the 1-star rate of late orders.</li>
<li><strong>Unit:</strong> customer (customer_unique_id), 50/50. Low interference: one customer's message does not
change another's delivery. Seller-level randomisation would cut the number of units for no gain.</li>
<li><strong>Primary metric:</strong> 1-star rate of flagged late orders (baseline {pct(m['exp_p_one_star_late'])}).</li>
<li><strong>Guardrails:</strong> review response rate ({pct(m['exp_review_rate_late'])} today), cancellations,
service contacts, delivery time.</li>
<li><strong>Not primary:</strong> repeat purchase. It would need {m['exp_n_per_arm_repeat']:,.0f} first orders per arm.</li>
<li><strong>Pitfalls handled:</strong> fixed sample size (no peeking), daily sample ratio mismatch check,
novelty check across halves, analysis limited to flagged orders.</li>
</ul>
<p>Full design: <code>docs/experiment_design.md</code>.</p>
</div>"""
    tiles = [("Orders per arm", f"{m['exp_n_per_arm']:,.0f}"), ("Total orders", f"{m['exp_n_total']:,.0f}"),
             ("Duration", f"{m['exp_months']:.1f} months"),
             ("Detectable effect", f"{100 * m['exp_p_one_star_late']:.1f}% to {100 * m['exp_p_one_star_treat']:.1f}%")]
    return tiles, design + chart(fig1, "e1") + chart(fig2, "e2")


def chart(fig, div_id, note=None):
    n = f'<p class="note">{html.escape(note)}</p>' if note else ""
    return f'<div class="card">{div(fig, div_id)}{n}</div>'


def tiles_html(tiles):
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="tile-label">{html.escape(a)}</div><div class="tile-value">{html.escape(b)}</div></div>'
        for a, b in tiles) + "</div>"


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Promise Gap</title>
<script src="https://cdn.plot.ly/plotly-__PLOTLY_VERSION__.min.js" charset="utf-8"></script>
<style>
:root {
  color-scheme: light;
  --surface-0: #f4f4f2; --surface-1: #fcfcfb; --border: #e2e1dc;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #6f6e69;
  --grid: #e7e6e1; --accent: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --border: #2e2e2c;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #9a998f;
    --grid: #2b2b29; --accent: #3987e5;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --border: #2e2e2c;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #9a998f;
  --grid: #2b2b29; --accent: #3987e5;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 15px/1.5 Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }
header, main { max-width: 1100px; margin: 0 auto; padding: 0 16px; }
header { padding-top: 28px; }
h1 { font-size: 28px; margin: 0 0 4px; }
.lede { color: var(--text-secondary); margin: 0 0 16px; max-width: 760px; }
.qa { display: grid; gap: 8px; margin-bottom: 16px; }
.qa div { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; }
.qa b { color: var(--text-secondary); font-weight: 600; margin-right: 6px; }
nav { display: flex; gap: 4px; border-bottom: 1px solid var(--border); overflow-x: auto; position: sticky; top: 0;
  background: var(--surface-0); z-index: 5; }
nav button { background: none; border: 0; border-bottom: 2px solid transparent; color: var(--text-secondary);
  padding: 10px 14px; font: inherit; cursor: pointer; white-space: nowrap; }
nav button[aria-selected="true"] { color: var(--text-primary); border-bottom-color: var(--accent); font-weight: 600; }
section { display: none; padding: 16px 0 40px; }
section.active { display: block; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile, .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; }
.tile { padding: 12px 14px; }
.tile-label { color: var(--text-secondary); font-size: 13px; }
.tile-value { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card { padding: 12px; margin-bottom: 16px; overflow: hidden; }
.note { color: var(--text-muted); font-size: 13px; margin: 4px 8px 4px; }
.prose { padding: 12px 20px; }
.prose li { margin-bottom: 6px; }
code { font-size: 13px; }
footer { color: var(--text-muted); font-size: 13px; max-width: 1100px; margin: 0 auto; padding: 0 16px 40px; }
.theme { float: right; background: var(--surface-1); color: var(--text-secondary); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 10px; font: inherit; font-size: 13px; cursor: pointer; }
</style>
</head>
<body>
<header>
<button class="theme" id="theme" type="button">Theme</button>
<h1>The Promise Gap</h1>
<p class="lede">Do late deliveries cause bad reviews and lost repeat purchases on the Olist marketplace,
and what should Olist test to fix it? Built from the public Olist data (__DATA_RANGE__).</p>
<div class="qa">
<div><b>Answer</b>__ANSWER__</div>
<div><b>Recommendation</b>__RECOMMENDATION__</div>
</div>
</header>
<main>
<nav role="tablist">
<button role="tab" aria-selected="true" data-tab="funnel">Funnel</button>
<button role="tab" aria-selected="false" data-tab="cohorts">Cohorts</button>
<button role="tab" aria-selected="false" data-tab="promise">Promise Gap</button>
<button role="tab" aria-selected="false" data-tab="experiment">Experiment Plan</button>
</nav>
<section id="funnel" class="active">__FUNNEL__</section>
<section id="cohorts">__COHORTS__</section>
<section id="promise">__PROMISE__</section>
<section id="experiment">__EXPERIMENT__</section>
</main>
<footer>Every number on this page is generated by <code>python run_all.py</code> from the raw data.
Source: Olist Brazilian E-Commerce and Marketing Funnel datasets on Kaggle.</footer>
<script>
(function () {
  const root = document.documentElement;
  function css(v) { return getComputedStyle(root).getPropertyValue(v).trim(); }
  function themeCharts() {
    const ink = css('--text-secondary'), grid = css('--grid'), surf = css('--surface-1');
    document.querySelectorAll('.js-plotly-plot').forEach(function (g) {
      Plotly.relayout(g, {'font.color': ink, 'title.font.color': css('--text-primary'),
        'xaxis.gridcolor': grid, 'yaxis.gridcolor': grid, 'xaxis.linecolor': grid, 'yaxis.linecolor': grid,
        'hoverlabel.bgcolor': surf, 'hoverlabel.font.color': css('--text-primary')});
    });
  }
  function show(id) {
    document.querySelectorAll('nav button').forEach(function (b) {
      b.setAttribute('aria-selected', b.dataset.tab === id ? 'true' : 'false'); });
    document.querySelectorAll('section').forEach(function (s) { s.classList.toggle('active', s.id === id); });
    document.querySelectorAll('#' + id + ' .js-plotly-plot').forEach(function (g) { Plotly.Plots.resize(g); });
    try { localStorage.setItem('tab', id); } catch (e) {}
  }
  document.querySelectorAll('nav button').forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.tab); }); });
  document.getElementById('theme').addEventListener('click', function () {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('theme', root.dataset.theme); } catch (e) {}
    themeCharts();
  });
  window.addEventListener('load', function () {
    try { const t = localStorage.getItem('theme'); if (t) root.dataset.theme = t; } catch (e) {}
    themeCharts();
    try { const tab = localStorage.getItem('tab'); if (tab && document.getElementById(tab)) show(tab); } catch (e) {}
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', themeCharts);
})();
</script>
</body>
</html>
"""


def main(m, answer, recommendation):
    pages = {}
    for key, fn in [("FUNNEL", funnel_page), ("COHORTS", cohort_page), ("PROMISE", promise_page),
                    ("EXPERIMENT", experiment_page)]:
        tiles, body = fn(m)
        pages[key] = tiles_html(tiles) + body
    out = (PAGE.replace("__PLOTLY_VERSION__", get_plotlyjs_version())
           .replace("__DATA_RANGE__", f"orders from {m['data_start']} to {m['data_end']}")
           .replace("__ANSWER__", html.escape(answer))
           .replace("__RECOMMENDATION__", html.escape(recommendation)))
    for k, v in pages.items():
        out = out.replace(f"__{k}__", v)
    (config.DOCS / "index.html").write_text(out, encoding="utf-8")
    return config.DOCS / "index.html"
