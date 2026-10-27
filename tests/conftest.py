"""Toy data with answers that can be worked out by hand.

The real SQL in sql/ is run against these tables, so the tests check the
production logic, not a copy of it.

Customers (customer_unique_id) and their orders:
  U1: o1 delivered 2017-01-10 (on time, two items, two reviews)
      o2 delivered 2017-03-05 (2 days late, 1 star)        -> repeat buyer
  U2: o3 canceled 2017-01-20, o7 delivered 2017-04-01      -> first delivered order is o7
  U3: o4 shipped, never delivered
  U4: o5 delivered 2017-02-10, o9 delivered same day       -> NOT a repeat (same day)
  U5: o6 created, nothing else
  U6: o8 delivered 2017-09-30                              -> data end, window not observed
"""
import pandas as pd
import pytest

from src import db

ORDERS = [
    # order_id, customer_id, status, purchase, approved, carrier, delivered, estimated
    ("o1", "c1", "delivered", "2017-01-10 10:00:00", "2017-01-10 10:30:00", "2017-01-11 10:00:00",
     "2017-01-15 10:00:00", "2017-01-20 00:00:00"),
    ("o2", "c2", "delivered", "2017-03-05 09:00:00", "2017-03-05 09:10:00", "2017-03-06 09:00:00",
     "2017-03-12 18:00:00", "2017-03-10 00:00:00"),
    ("o3", "c3", "canceled", "2017-01-20 12:00:00", "2017-01-20 13:00:00", None, None, "2017-02-05 00:00:00"),
    ("o4", "c4", "shipped", "2017-02-01 08:00:00", "2017-02-01 09:00:00", "2017-02-02 08:00:00", None,
     "2017-02-20 00:00:00"),
    ("o5", "c5", "delivered", "2017-02-10 08:00:00", "2017-02-10 08:30:00", None,
     "2017-02-18 12:00:00", "2017-02-20 00:00:00"),
    ("o6", "c6", "created", "2017-02-15 08:00:00", None, None, None, "2017-03-01 00:00:00"),
    ("o7", "c7", "delivered", "2017-04-01 08:00:00", "2017-04-01 09:00:00", "2017-04-02 08:00:00",
     "2017-04-10 08:00:00", "2017-04-10 00:00:00"),
    ("o8", "c8", "delivered", "2017-09-30 08:00:00", "2017-09-30 09:00:00", "2017-10-01 08:00:00",
     "2017-10-05 08:00:00", "2017-10-20 00:00:00"),
    ("o9", "c9", "delivered", "2017-02-10 20:00:00", "2017-02-10 20:30:00", "2017-02-11 08:00:00",
     "2017-02-15 08:00:00", "2017-02-25 00:00:00"),
]
CUSTOMERS = [("c1", "U1", "SP"), ("c2", "U1", "SP"), ("c3", "U2", "RJ"), ("c4", "U3", "MG"),
             ("c5", "U4", "SP"), ("c6", "U5", "BA"), ("c7", "U2", "RJ"), ("c8", "U6", "SP"),
             ("c9", "U4", "SP")]
ITEMS = [
    # order_id, item, product, seller, price, freight
    ("o1", 1, "p1", "s1", 50.0, 10.0),
    ("o1", 2, "p2", "s2", 80.0, 12.0),    # most expensive -> order category health_beauty, seller s2
    ("o2", 1, "p1", "s2", 40.0, 8.0),
    ("o5", 1, "p1", "s2", 30.0, 5.0),
    ("o7", 1, "p1", "s1", 20.0, 5.0),
    ("o8", 1, "p1", "s1", 25.0, 5.0),
    ("o9", 1, "p1", "s2", 15.0, 5.0),
]
REVIEWS = [
    # review_id, order_id, score, created, answered
    ("r1", "o1", 3, "2017-01-16 00:00:00", "2017-01-16 10:00:00"),
    ("r2", "o1", 5, "2017-01-17 00:00:00", "2017-01-18 10:00:00"),   # latest answered -> kept
    ("r3", "o2", 1, "2017-03-11 00:00:00", "2017-03-11 12:00:00"),   # sent before delivery (03-12)
    ("r4", "o7", 4, "2017-04-11 00:00:00", "2017-04-12 10:00:00"),
    ("r5", "o3", 2, "2017-01-25 00:00:00", "2017-01-25 10:00:00"),   # review on a canceled order
]
PRODUCTS = [("p1", "cama_mesa_banho"), ("p2", "beleza_saude")]
TRANSLATION = [("cama_mesa_banho", "bed_bath_table"), ("beleza_saude", "health_beauty")]
SELLERS = [("s1", "SP"), ("s2", "PR"), ("s9", "SP")]
MQL = [("m1", "2017-01-01", "organic_search"), ("m2", "2017-01-15", "paid_search"), ("m3", "2017-02-01", None)]
DEALS = [("m1", "s1", "2017-01-05 10:00:00", "home"), ("m2", "s9", "2017-02-01 10:00:00", "toys")]


def frames():
    as_str = lambda df: df.astype(object).where(df.notna(), None).astype("string")
    return {
        "raw_orders": pd.DataFrame(ORDERS, columns=[
            "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
            "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]),
        "raw_customers": pd.DataFrame([(c, u, "01000", "city", s) for c, u, s in CUSTOMERS], columns=[
            "customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]),
        "raw_order_items": pd.DataFrame([(o, i, p, s, "2017-01-01 00:00:00", pr, f) for o, i, p, s, pr, f in ITEMS],
                                        columns=["order_id", "order_item_id", "product_id", "seller_id",
                                                 "shipping_limit_date", "price", "freight_value"]),
        "raw_order_reviews": pd.DataFrame([(r, o, s, None, None, c, a) for r, o, s, c, a in REVIEWS], columns=[
            "review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
            "review_creation_date", "review_answer_timestamp"]),
        "raw_order_payments": pd.DataFrame([("o1", 1, "credit_card", 1, 152.0)], columns=[
            "order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]),
        "raw_products": pd.DataFrame([(p, c, 10, 100, 1, 500, 10, 10, 10) for p, c in PRODUCTS], columns=[
            "product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
            "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm",
            "product_width_cm"]),
        "raw_sellers": pd.DataFrame([(s, "01000", "city", st) for s, st in SELLERS], columns=[
            "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]),
        "raw_geolocation": pd.DataFrame([("01000", -23.5, -46.6, "city", "SP")], columns=[
            "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city",
            "geolocation_state"]),
        "raw_category_translation": pd.DataFrame(TRANSLATION, columns=[
            "product_category_name", "product_category_name_english"]),
        "raw_mql": pd.DataFrame(MQL, columns=["mql_id", "first_contact_date", "origin"]).assign(
            landing_page_id="lp1")[["mql_id", "first_contact_date", "landing_page_id", "origin"]],
        "raw_closed_deals": pd.DataFrame([(m, s, "sdr", "sr", w, seg, "online", "cat", True, False, None,
                                           "reseller", None, 0.0) for m, s, w, seg in DEALS], columns=[
            "mql_id", "seller_id", "sdr_id", "sr_id", "won_date", "business_segment", "lead_type",
            "lead_behaviour_profile", "has_company", "has_gtin", "average_stock",
            "business_type", "declared_product_catalog_size", "declared_monthly_revenue"]),
    }, as_str


@pytest.fixture(scope="session")
def toy():
    """In-memory warehouse built by the real SQL from the toy raw tables."""
    con = db.connect(":memory:")
    tables, as_str = frames()
    for name, df in tables.items():
        con.register("tmp", as_str(df))
        con.execute(f"create table {name} as select * from tmp")   # all text, like the raw CSV views
        con.unregister("tmp")
    db.build(con)
    yield con
    con.close()
