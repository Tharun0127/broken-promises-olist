"""Section 8a: star schema CSVs for Power BI, plus the build guide with expected values."""
from src import config

DATA = config.POWERBI / "data"

FACT_ORDERS = """
select
    o.order_id,
    o.customer_unique_id                                  as customer_key,
    coalesce(o.main_seller_id, 'no_items')                as seller_key,
    o.category_en                                         as category_key,
    cast(strftime(o.purchased_at, '%Y%m%d') as integer)   as purchase_date_key,
    o.order_status,
    -- Cumulative stage flags, same rule as sql/marts/02_mart_fulfilment_funnel.sql
    1                                                                         as is_purchased,
    (o.is_delivered or o.shipped_at is not null or o.approved_at is not null)::int as is_approved,
    (o.is_delivered or o.shipped_at is not null)::int                         as is_shipped,
    o.is_delivered::int                                                       as is_delivered,
    (o.is_delivered and o.review_id is not null)::int                         as is_reviewed,
    date_diff('second', o.purchased_at, o.approved_at) / 3600.0               as hours_purchase_to_approve,
    date_diff('second', o.approved_at, o.shipped_at) / 3600.0                 as hours_approve_to_ship,
    date_diff('second', o.shipped_at, o.delivered_at) / 3600.0                as hours_ship_to_deliver,
    o.order_value,
    o.items_value,
    o.freight_value,
    o.n_items,
    -- Promise gap fields: only for delivered orders (the analysis grain).
    p.days_late,
    p.is_late::int                                        as is_late,
    p.promised_days,
    p.review_score,
    p.one_star,
    p.review_before_delivery::int                         as review_before_delivery,
    p.is_first_order::int                                 as is_first_order,
    p.repeat_180
from int_orders o
left join mart_promise_gap p using (order_id)
"""

DIM_CUSTOMER = """
with all_customers as (
    -- Every person in the fact table, including those with no delivered order.
    select customer_unique_id, any_value(customer_state) as any_state
    from int_orders group by 1
)
select
    a.customer_unique_id                               as customer_key,
    coalesce(c.customer_state, a.any_state)            as customer_state,
    c.cohort_month,
    c.first_purchase_date,
    coalesce(c.n_orders, 0)                            as delivered_orders,
    (c.customer_unique_id is not null)::int            as has_delivered_order,
    coalesce(c.is_repeat_customer, false)::int         as is_repeat_customer,
    c.repeat_window_observed::int                      as repeat_window_observed,
    c.repeat_in_window::int                            as repeat_in_180d
from all_customers a
left join mart_customers c using (customer_unique_id)
"""

DIM_SELLER = """
with first_sale as (
    select seller_id, min(purchase_date) as first_sale_date from mart_seller_sales group by 1
)
select
    s.seller_id                                        as seller_key,
    s.seller_state,
    s.seller_city,
    f.first_sale_date,
    date_trunc('month', f.first_sale_date)::date       as seller_cohort_month,
    coalesce(m.lead_origin, 'not_from_lead_data')      as lead_origin,
    coalesce(d.business_segment, 'not_from_lead_data') as business_segment
from stg_sellers s
left join first_sale f using (seller_id)
left join stg_closed_deals d using (seller_id)
left join stg_mql m on m.mql_id = d.mql_id
union all
select 'no_items', null, null, null, null, 'not_from_lead_data', 'not_from_lead_data'
"""

DIM_DATE = """
with bounds as (
    select min(purchased_at)::date as d0, max(purchased_at)::date as d1 from stg_orders
)
select
    cast(strftime(d, '%Y%m%d') as integer) as date_key,
    d::date                                as date,
    year(d)                                as year,
    'Q' || quarter(d)                      as quarter,
    month(d)                               as month_number,
    strftime(d, '%b')                      as month_name,
    strftime(d, '%Y-%m')                   as year_month,
    isodow(d)                              as weekday_number
from bounds, generate_series(d0, d1, interval 1 day) as t(d)
"""

DIM_CATEGORY = """
select distinct
    category_en as category_key,
    category_pt,
    category_en as category_name
from int_orders
"""

AGGREGATES = {
    # Things DAX cannot recompute from the star schema (model outputs, leads data).
    "agg_customer_cohorts": "select * from mart_customer_cohorts",
    "agg_seller_cohorts": "select * from mart_seller_cohorts",
    "agg_seller_funnel": "select * from mart_seller_funnel",
}

CSV_AGGREGATES = {
    "agg_rd_results": "rd_results.csv",
    "agg_rd_curve": "rd_descriptive_curve.csv",
    "agg_rd_order_counts": "rd_order_counts_by_day.csv",
    "agg_rd_balance": "rd_balance.csv",
    "agg_sizing": "sizing.csv",
    "agg_experiment_power": "experiment_power.csv",
}


def main(con):
    import pandas as pd
    DATA.mkdir(parents=True, exist_ok=True)
    tables = {"fact_orders": FACT_ORDERS, "dim_customer": DIM_CUSTOMER, "dim_seller": DIM_SELLER,
              "dim_date": DIM_DATE, "dim_category": DIM_CATEGORY, **AGGREGATES}
    counts = {}
    for name, sql in tables.items():
        df = con.execute(sql).df()
        df.to_csv(DATA / f"{name}.csv", index=False)
        counts[name] = len(df)
    for name, src in CSV_AGGREGATES.items():
        df = pd.read_csv(config.OUTPUTS / src)
        df.to_csv(DATA / f"{name}.csv", index=False)
        counts[name] = len(df)

    # Referential integrity: every fact key must exist in its dimension.
    checks = {
        "customer": "select count(*) from ({f}) f left join ({d}) d using (customer_key) where d.customer_key is null",
        "seller": "select count(*) from ({f}) f left join ({d}) d using (seller_key) where d.seller_key is null",
        "category": "select count(*) from ({f}) f left join ({d}) d using (category_key) where d.category_key is null",
        "date": "select count(*) from ({f}) f left join ({d}) d on d.date_key = f.purchase_date_key where d.date_key is null",
    }
    dims = {"customer": DIM_CUSTOMER, "seller": DIM_SELLER, "category": DIM_CATEGORY, "date": DIM_DATE}
    orphans = {k: con.execute(v.format(f=FACT_ORDERS, d=dims[k])).fetchone()[0] for k, v in checks.items()}
    # Primary keys must be unique.
    dupes = {
        "dim_customer": con.execute(f"select count(*) - count(distinct customer_key) from ({DIM_CUSTOMER})").fetchone()[0],
        "dim_seller": con.execute(f"select count(*) - count(distinct seller_key) from ({DIM_SELLER})").fetchone()[0],
        "dim_category": con.execute(f"select count(*) - count(distinct category_key) from ({DIM_CATEGORY})").fetchone()[0],
        "dim_date": con.execute(f"select count(*) - count(distinct date_key) from ({DIM_DATE})").fetchone()[0],
    }
    bad = {k: v for k, v in {**orphans, **dupes}.items() if v}
    if bad:
        raise AssertionError(f"Star schema integrity failed: {bad}")
    return counts
