"""Builds and executes notebooks/walkthrough.ipynb against the warehouse built by run_all.py."""
import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from src import config

CELLS = [
    ("md", """# The Promise Gap: walkthrough

This notebook walks through the analysis end to end, reading the DuckDB warehouse that
`python run_all.py` builds. Every number here is computed live from the data.

Question: do late deliveries cause bad reviews and lost repeat purchases on Olist, and what should Olist test?"""),
    ("code", """import json, os, sys
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()
os.chdir(ROOT); sys.path.insert(0, str(ROOT))
import duckdb, pandas as pd, numpy as np
import plotly.graph_objects as go
from src import config, rd
pd.set_option('display.width', 160); pd.set_option('display.max_columns', 20)
con = duckdb.connect(str(config.DB_PATH), read_only=True)
m = json.loads((config.OUTPUTS / 'metrics.json').read_text())
q = lambda sql: con.execute(sql).df()"""),
    ("md", """## 1. Data profile

The key limitations: data ends in August 2018, 2016 is sparse, `customer_id` is per order,
and most late orders are reviewed before they arrive. Full detail in `docs/data_profile.md`."""),
    ("code", """pd.read_csv(config.OUTPUTS / 'profile' / 'tables.csv')"""),
    ("code", """# Why customer_unique_id: customer_id has one value per order.
q('''select count(distinct customer_id) as customer_ids,
            count(distinct customer_unique_id) as people
     from stg_customers''')"""),
    ("md", """## 2. The clean model and exclusions

Grain: one row per delivered order. Every step that drops rows is logged."""),
    ("code", """q('select * from int_exclusions order by step')"""),
    ("md", """## 3. Funnels

Stages are cumulative: an order that reached a later stage counts as having reached the earlier ones."""),
    ("code", """print((config.SQL_DIR / 'marts' / '02_mart_fulfilment_funnel.sql').read_text()[:1500])"""),
    ("code", """q('''select dimension_value, n_purchased, n_approved, n_shipped, n_delivered, n_reviewed,
            round(conv_purchased_to_delivered, 4) as delivered_rate,
            round(median_h_ship_to_deliver, 1) as median_h_ship_to_deliver
     from mart_fulfilment_funnel where dimension = 'overall' ''')"""),
    ("code", """q('''select dimension_value, n_leads, n_closed, n_first_sale, n_first_sale_observed, n_still_selling,
            round(conv_lead_to_closed, 3) lead_to_closed, round(conv_closed_to_first_sale, 3) closed_to_sale,
            round(conv_first_sale_to_still_selling, 3) still_selling
     from mart_seller_funnel where dimension in ('overall', 'lead_origin') order by n_closed desc''')"""),
    ("md", """## 4. Cohort retention

Unobserved cells are NULL, not zero. The curve pools only cohorts that have reached each month."""),
    ("code", """tri = pd.read_csv(config.OUTPUTS / 'cohort_customers_triangle.csv', index_col=0)
(tri.iloc[:, :8] * 100).round(2)"""),
    ("code", """print(f"Repeat rate, all customers, any time: {m['repeat_rate_all_time']:.2%}")
print(f"Repeat within 180 days (full window observed): {m['repeat_rate_180d']:.2%} of {m['repeat_rate_180d_base']:,} customers")
pd.read_csv(config.OUTPUTS / 'retention_curve_customers.csv').head(13)"""),
    ("md", """## 5. The promise gap

First the descriptive picture: outcome by days late."""),
    ("code", """df = q('select * from mart_promise_gap')
curve = df[df.days_late.between(-10, 15)].groupby('days_late').agg(
    orders=('order_id', 'size'), one_star=('one_star', 'mean'),
    review_before_delivery=('review_before_delivery', 'mean'), repeat_180=('repeat_180', 'mean'))
curve.round(3)"""),
    ("code", """fig = go.Figure()
c = curve.reset_index()
fig.add_trace(go.Scatter(x=c.days_late, y=c.one_star, mode='markers+lines', name='1-star rate'))
fig.add_trace(go.Scatter(x=c.days_late, y=c.review_before_delivery, mode='markers+lines', name='Surveyed before delivery'))
fig.add_vline(x=0.5, line_dash='dash')
fig.update_layout(title='1-star rate rises with each day late; surveys start arriving before the parcel at day 3',
                  xaxis_title='Days late', yaxis_tickformat='.0%', height=420)
fig"""),
    ("md", """Now the regression discontinuity. Bandwidth chosen by leave-one-out cross-validation,
then the local linear jump with HC1 standard errors. This re-runs the estimator live."""),
    ("code", """h, cv = rd.cv_bandwidth(df.days_late.values, df.one_star.values)
print('Chosen bandwidth:', h)
rows = []
for name in ['one_star', 'review_score', 'repeat_180']:
    r = rd.local_linear_rd(df.days_late.values, df[name].values, h=h)
    a = rd.adjacent_days(df.days_late.values, df[name].values)
    rows.append({'outcome': name, 'rd_jump': r['estimate'], 'ci_low': r['ci_low'], 'ci_high': r['ci_high'],
                 'p': r['p_value'], 'day1_vs_day0': a['estimate']})
pd.DataFrame(rows).round(4)"""),
    ("code", """# Validity checks
print('Density:', {k: round(v, 3) for k, v in rd.density_test(df.days_late.values, h=h).items()})
pd.read_csv(config.OUTPUTS / 'rd_balance.csv')[['covariate', 'estimate', 'p_value']].round(4)"""),
    ("md", """Reading: no sharp jump at the promise date once the trend is modelled, but a steep ramp over
the next three days. Density and balance checks partly fail, so the local estimate carries a caveat.
This is a local effect at the promise date, not the effect of being a week late."""),
    ("md", """## 6. Business sizing"""),
    ("code", """pd.read_csv(config.OUTPUTS / 'sizing.csv').round(2)"""),
    ("md", """## 7. Experiment design (not run)"""),
    ("code", """pd.read_csv(config.OUTPUTS / 'experiment_power.csv').round(2)"""),
    ("code", """print(f"Primary metric baseline (1-star among late orders): {m['exp_p_one_star_late']:.1%}")
print(f"Required per arm: {m['exp_n_per_arm']:,}  total: {m['exp_n_total']:,}  months: {m['exp_months']:.1f}")"""),
    ("code", """con.close()"""),
]


def main():
    nb = new_notebook()
    nb.cells = [new_markdown_cell(src) if kind == "md" else new_code_cell(src) for kind, src in CELLS]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    config.NOTEBOOKS.mkdir(exist_ok=True)
    client = NotebookClient(nb, timeout=600, kernel_name="python3",
                            resources={"metadata": {"path": str(config.NOTEBOOKS)}})
    client.execute()
    path = config.NOTEBOOKS / "walkthrough.ipynb"
    nbformat.write(nb, path)
    return path


if __name__ == "__main__":
    print(main())
