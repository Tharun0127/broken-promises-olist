"""Section 1: data profile.

Writes docs/data_profile.md and outputs/profile/*.csv. Every number in the
markdown is computed here from the staging views.
"""
import json

import pandas as pd

from src import config
from src.db import connect, register_raw, run_layer, write_params

OUT = config.OUTPUTS / "profile"

# Table -> (staging view, primary key columns)
TABLES = {
    "orders": ("stg_orders", ["order_id"]),
    "order_items": ("stg_order_items", ["order_id", "order_item_id"]),
    "customers": ("stg_customers", ["customer_id"]),
    "order_reviews": ("stg_order_reviews", ["review_id", "order_id"]),
    "order_payments": ("stg_order_payments", ["order_id", "payment_sequential"]),
    "products": ("stg_products", ["product_id"]),
    "sellers": ("stg_sellers", ["seller_id"]),
    "category_translation": ("stg_category_translation", ["category_pt"]),
    "geolocation": ("stg_geolocation", ["zip_prefix", "lat", "lng"]),
    "mql": ("stg_mql", ["mql_id"]),
    "closed_deals": ("stg_closed_deals", ["mql_id"]),
}

DATE_COLUMNS = {
    "stg_orders": ["purchased_at", "approved_at", "shipped_at", "delivered_at",
                   "estimated_delivery_date"],
    "stg_order_reviews": ["review_sent_date", "review_answered_at"],
    "stg_mql": ["first_contact_date"],
    "stg_closed_deals": ["won_at"],
}


def q(con, sql):
    return con.execute(sql).df()


def table_overview(con):
    rows = []
    for name, (view, keys) in TABLES.items():
        k = ", ".join(keys)
        r = con.execute(f"""
            select count(*) as n_rows,
                   (select count(*) from (select distinct {k} from {view})) as n_distinct_key,
                   (select count(*) from (select distinct * from {view})) as n_distinct_rows
            from {view}""").fetchone()
        rows.append({"table": name, "rows": r[0], "primary_key": k,
                     "distinct_keys": r[1], "duplicate_key_rows": r[0] - r[1],
                     "exact_duplicate_rows": r[0] - r[2]})
    return pd.DataFrame(rows)


def null_report(con):
    rows = []
    for name, (view, _) in TABLES.items():
        cols = q(con, f"describe {view}")["column_name"].tolist()
        exprs = ", ".join(f'count(*) - count("{c}") as "{c}"' for c in cols)
        counts = con.execute(f"select count(*), {exprs} from {view}").fetchone()
        total = counts[0]
        for c, n_null in zip(cols, counts[1:]):
            if n_null:
                rows.append({"table": name, "column": c, "nulls": n_null,
                             "null_pct": round(100 * n_null / total, 2)})
    return pd.DataFrame(rows)


def date_ranges(con):
    rows = []
    for view, cols in DATE_COLUMNS.items():
        for c in cols:
            r = con.execute(f"select min({c}), max({c}), count({c}) from {view}").fetchone()
            rows.append({"table": view, "column": c, "min": str(r[0]), "max": str(r[1]),
                         "non_null": r[2]})
    return pd.DataFrame(rows)


def join_cardinality(con):
    """Each check answers: how many rows on the left find 0, 1 or many matches."""
    checks = {
        "orders -> customers (customer_id)": """
            select count(*) filter (where n = 0) zero, count(*) filter (where n = 1) one,
                   count(*) filter (where n > 1) many
            from (select o.order_id, count(c.customer_id) n from stg_orders o
                  left join stg_customers c using (customer_id) group by 1)""",
        "orders -> order_items": """
            select count(*) filter (where n = 0), count(*) filter (where n = 1),
                   count(*) filter (where n > 1)
            from (select o.order_id, count(i.order_id) n from stg_orders o
                  left join stg_order_items i using (order_id) group by 1)""",
        "orders -> order_reviews": """
            select count(*) filter (where n = 0), count(*) filter (where n = 1),
                   count(*) filter (where n > 1)
            from (select o.order_id, count(r.order_id) n from stg_orders o
                  left join stg_order_reviews r using (order_id) group by 1)""",
        "orders -> order_payments": """
            select count(*) filter (where n = 0), count(*) filter (where n = 1),
                   count(*) filter (where n > 1)
            from (select o.order_id, count(p.order_id) n from stg_orders o
                  left join stg_order_payments p using (order_id) group by 1)""",
        "order_items -> products": """
            select count(*) filter (where p.product_id is null), count(*) filter (where p.product_id is not null), 0
            from stg_order_items i left join stg_products p using (product_id)""",
        "order_items -> sellers": """
            select count(*) filter (where s.seller_id is null), count(*) filter (where s.seller_id is not null), 0
            from stg_order_items i left join stg_sellers s using (seller_id)""",
        "products -> category_translation": """
            select count(*) filter (where t.category_pt is null), count(*) filter (where t.category_pt is not null), 0
            from stg_products p left join stg_category_translation t using (category_pt)""",
        "customer_unique_id -> customer_id": """
            select 0, count(*) filter (where n = 1), count(*) filter (where n > 1)
            from (select customer_unique_id, count(*) n from stg_customers group by 1)""",
        "review_id -> orders": """
            select 0, count(*) filter (where n = 1), count(*) filter (where n > 1)
            from (select review_id, count(distinct order_id) n from stg_order_reviews group by 1)""",
        "closed_deals -> mql (mql_id)": """
            select count(*) filter (where m.mql_id is null), count(*) filter (where m.mql_id is not null), 0
            from stg_closed_deals d left join stg_mql m using (mql_id)""",
        "closed_deals -> order_items (seller_id has any sale)": """
            select count(*) filter (where s.seller_id is null), count(*) filter (where s.seller_id is not null), 0
            from stg_closed_deals d
            left join (select distinct seller_id from stg_order_items) s using (seller_id)""",
    }
    rows = []
    for label, sql in checks.items():
        z, one, many = con.execute(sql).fetchone()
        rows.append({"join": label, "no_match": z, "exactly_one": one, "many": many})
    return pd.DataFrame(rows)


def status_and_dates(con):
    status = q(con, """
        select order_status, count(*) as orders,
               round(100.0 * count(*) / sum(count(*)) over (), 2) as pct,
               count(*) filter (where delivered_at is null) as missing_delivered_date,
               count(*) filter (where estimated_delivery_date is null) as missing_estimated_date,
               count(*) filter (where approved_at is null) as missing_approved,
               count(*) filter (where shipped_at is null) as missing_shipped
        from stg_orders group by 1 order by orders desc""")
    monthly = q(con, """
        select strftime(purchased_at, '%Y-%m') as purchase_month, count(*) as orders,
               count(*) filter (where order_status = 'delivered') as delivered
        from stg_orders group by 1 order by 1""")
    return status, monthly


def facts(con):
    """Scalar facts used in the limitations list."""
    f = {}
    one = lambda s: con.execute(s).fetchone()[0]
    f["orders"] = one("select count(*) from stg_orders")
    f["delivered_status"] = one("select count(*) from stg_orders where order_status='delivered'")
    f["delivered_missing_date"] = one(
        "select count(*) from stg_orders where order_status='delivered' and delivered_at is null")
    f["not_delivered_with_date"] = one(
        "select count(*) from stg_orders where order_status<>'delivered' and delivered_at is not null")
    f["missing_estimate"] = one("select count(*) from stg_orders where estimated_delivery_date is null")
    f["last_purchase"] = str(one("select max(purchased_at) from stg_orders where order_status='delivered'"))
    f["orders_after_aug_2018"] = one("select count(*) from stg_orders where purchased_at >= '2018-09-01'")
    f["orders_2016"] = one("select count(*) from stg_orders where purchased_at < '2017-01-01'")
    f["unique_customers"] = one("select count(distinct customer_unique_id) from stg_customers")
    f["customer_ids"] = one("select count(*) from stg_customers")
    f["orders_multi_review"] = one(
        "select count(*) from (select order_id from stg_order_reviews group by 1 having count(*) > 1)")
    f["reviews_shared_id"] = one(
        "select count(*) from (select review_id from stg_order_reviews group by 1 having count(distinct order_id) > 1)")
    f["products_no_category"] = one("select count(*) from stg_products where category_pt is null")
    f["categories_no_translation"] = one("""
        select count(distinct p.category_pt) from stg_products p
        left join stg_category_translation t using (category_pt)
        where p.category_pt is not null and t.category_pt is null""")
    f["orders_no_items"] = one(
        "select count(*) from stg_orders o where not exists (select 1 from stg_order_items i where i.order_id=o.order_id)")
    f["late_delivered_share"] = one("""
        select avg((delivered_at::date > estimated_delivery_date)::int) from stg_orders
        where order_status='delivered' and delivered_at is not null""")
    f["late_review_before_delivery"] = one("""
        select avg((r.review_sent_date < o.delivered_at::date)::int)
        from stg_orders o join stg_order_reviews r using (order_id)
        where o.order_status='delivered' and o.delivered_at::date > o.estimated_delivery_date""")
    f["ontime_review_before_delivery"] = one("""
        select avg((r.review_sent_date < o.delivered_at::date)::int)
        from stg_orders o join stg_order_reviews r using (order_id)
        where o.order_status='delivered' and o.delivered_at::date <= o.estimated_delivery_date""")
    f["review_last_sent"] = str(one("select max(review_sent_date) from stg_order_reviews"))
    f["delivered_after_review_end"] = one("""
        select count(*) from stg_orders where order_status='delivered'
        and delivered_at::date > (select max(review_sent_date) from stg_order_reviews)""")
    f["review_rate_after_review_end"] = one("""
        select avg((r.order_id is not null)::int) from stg_orders o
        left join (select distinct order_id from stg_order_reviews) r using (order_id)
        where o.order_status='delivered'
        and o.delivered_at::date > (select max(review_sent_date) from stg_order_reviews)""")
    f["mql"] = one("select count(*) from stg_mql")
    f["closed_deals"] = one("select count(*) from stg_closed_deals")
    f["closed_with_sales"] = one("""
        select count(*) from stg_closed_deals d
        where exists (select 1 from stg_order_items i where i.seller_id = d.seller_id)""")
    f["mql_range"] = [str(x) for x in con.execute(
        "select min(first_contact_date), max(first_contact_date) from stg_mql").fetchone()]
    f["geo_rows"] = one("select count(*) from stg_geolocation")
    f["geo_zips"] = one("select count(distinct zip_prefix) from stg_geolocation")
    return f


def md(df):
    return df.to_markdown(index=False)


def write_markdown(overview, nulls, dates, joins, status, monthly, f):
    pct = lambda x: f"{100 * x:.1f}%"
    lim = [
        f"**The data ends on {f['last_purchase'][:10]}.** Only {f['orders_after_aug_2018']} orders "
        "were placed after August 2018 and none of them were delivered. Any metric that needs "
        "follow-up time (repeat purchase, retention, seller activity) is right censored near the end. "
        "Every such metric in this project only uses customers or sellers with the full window observed.",
        f"**2016 is almost empty.** {f['orders_2016']} orders were placed in 2016, with a gap in "
        "November and December. Cohort tables start in January 2017.",
        f"**customer_id is not a customer.** There are {f['customer_ids']:,} customer_id values but only "
        f"{f['unique_customers']:,} customer_unique_id values. customer_id is created per order, so using it "
        "would make every customer look like a one-time buyer.",
        f"**Reviews for late orders are mostly sent before the parcel arrives.** For late orders, "
        f"{pct(f['late_review_before_delivery'])} of reviews were created before the delivery date, "
        f"against {pct(f['ontime_review_before_delivery'])} for on-time orders. Olist appears to send the survey "
        "around the estimated date. A late order's review often rates a parcel that has not arrived yet.",
        f"**Status and timestamps disagree for a few orders.** {f['delivered_missing_date']} orders are "
        f"'delivered' with no delivery date, and {f['not_delivered_with_date']} orders that are not "
        "'delivered' do have one. The analysis grain requires both status and date.",
        f"**Some orders have more than one review** ({f['orders_multi_review']} orders), and "
        f"{f['reviews_shared_id']} review_id values are attached to more than one order. The model keeps "
        "one review per order (the latest answered).",
        f"**{f['orders_no_items']} orders have no items.** They are mostly unavailable or canceled orders "
        "and cannot be given a category.",
        f"**{f['products_no_category']} products have no category** and {f['categories_no_translation']} "
        "Portuguese categories have no English translation. Both are labelled explicitly rather than dropped.",
        f"**The seller funnel is small.** {f['mql']:,} leads, {f['closed_deals']} closed deals, and only "
        f"{f['closed_with_sales']} closed deals ever made a sale in the orders data. Leads were first "
        f"contacted between {f['mql_range'][0]} and {f['mql_range'][1]}, so the latest deals have little "
        "time to sell before the data ends.",
        "**There is no cost, margin or commission data.** Money is measured as order value (item price plus "
        "freight) paid by customers. Olist's own revenue share cannot be computed from this data.",
        "**There is no data on what customers were shown or told** (delivery messages, notifications, "
        "marketing). Any intervention effect has to be tested, not estimated, from this data.",
        f"**Geolocation is not used.** It has {f['geo_rows']:,} rows for {f['geo_zips']:,} zip prefixes, "
        "with many coordinates per prefix. State is used instead.",
    ]
    text = f"""# Data profile

Generated by `src/profile_data.py` from the raw Kaggle files. Do not edit by hand.

## Limitations that affect the analysis

{chr(10).join(f"{i}. {x}" for i, x in enumerate(lim, 1))}

## Tables, keys and duplicates

`duplicate_key_rows` counts rows that share a primary key with another row.
`exact_duplicate_rows` counts rows identical in every column.

{md(overview)}

## Join cardinality

How many rows on the left side of each join find no match, exactly one match, or many matches.

{md(joins)}

## Date ranges

{md(dates)}

## Order status, with missing dates

Late-delivery analysis needs both `delivered_at` and `estimated_delivery_date`.
Missing estimated dates: {f['missing_estimate']}. Delivered orders that were late: {pct(f['late_delivered_share'])}.

{md(status)}

## Orders by purchase month

{md(monthly)}

## Columns with nulls

{md(nulls)}
"""
    (config.DOCS / "data_profile.md").write_text(text, encoding="utf-8")


def main(con=None):
    con = con or connect()
    OUT.mkdir(parents=True, exist_ok=True)
    overview, nulls, dates = table_overview(con), null_report(con), date_ranges(con)
    joins = join_cardinality(con)
    status, monthly = status_and_dates(con)
    f = facts(con)
    for name, df in {"tables": overview, "nulls": nulls, "date_ranges": dates,
                     "joins": joins, "order_status": status, "monthly_orders": monthly}.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    (OUT / "facts.json").write_text(json.dumps(f, indent=2, default=str), encoding="utf-8")
    write_markdown(overview, nulls, dates, joins, status, monthly, f)
    return f


if __name__ == "__main__":
    c = connect()
    register_raw(c)
    write_params(c)
    run_layer(c, "staging")
    print(json.dumps(main(c), indent=2, default=str))
