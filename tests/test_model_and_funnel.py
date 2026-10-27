"""Known-answer tests for the clean model and both funnels (see conftest.py for the toy data)."""
import pandas as pd
import pytest


def row(con, sql):
    return con.execute(sql).df().iloc[0]


def test_grain_is_one_row_per_delivered_order(toy):
    ids = set(toy.execute("select order_id from int_delivered_orders").df().order_id)
    # o3 canceled, o4 shipped only, o6 created: all excluded.
    assert ids == {"o1", "o2", "o5", "o7", "o8", "o9"}


def test_order_category_and_seller_come_from_most_expensive_item(toy):
    r = row(toy, "select * from int_orders where order_id = 'o1'")
    assert r.category_en == "health_beauty"
    assert r.main_seller_id == "s2"
    assert r.items_value == pytest.approx(130.0)
    assert r.freight_value == pytest.approx(22.0)


def test_latest_answered_review_is_kept(toy):
    assert row(toy, "select review_score from int_order_review where order_id = 'o1'").review_score == 5


def test_days_late_uses_calendar_dates(toy):
    d = toy.execute("select order_id, days_late, is_late from int_delivered_orders").df().set_index("order_id")
    assert d.days_late.to_dict() == {"o1": -5, "o2": 2, "o5": -2, "o7": 0, "o8": -15, "o9": -10}
    # o7 arrived at 08:00 on the promised day: on time, not 0.33 days late.
    assert not d.loc["o7", "is_late"]
    assert d.is_late.sum() == 1


def test_review_before_delivery_flag(toy):
    d = toy.execute("select order_id, review_before_delivery from int_delivered_orders "
                    "where has_review").df().set_index("order_id").review_before_delivery
    assert d.to_dict() == {"o1": False, "o2": True, "o7": False}


def test_customer_sequence_uses_unique_id_and_same_day_is_not_repeat(toy):
    d = toy.execute("select order_id, customer_order_number, days_since_previous_order, repeat_in_window "
                    "from int_delivered_orders").df().set_index("order_id")
    assert d.loc["o2", "customer_order_number"] == 2          # U1's second order, different customer_id
    assert d.loc["o2", "days_since_previous_order"] == 54
    assert d.loc["o9", "customer_order_number"] == 2          # same day as o5
    assert d.loc["o9", "days_since_previous_order"] == 0
    assert d.loc["o1", "repeat_in_window"] == True            # noqa: E712
    assert d.loc["o5", "repeat_in_window"] == False           # same-day order does not count
    assert d.loc["o7", "repeat_in_window"] == False           # 2017-04-01 + 180 = 09-28, inside data
    assert pd.isna(d.loc["o8", "repeat_in_window"])          # bought on the last day: censored, not "no"


def test_data_window(toy):
    w = row(toy, "select * from int_data_window")
    assert str(w.data_end.date()) == "2017-09-30"
    assert str(w.last_complete_month.date()) == "2017-09-01"   # Sep 30 is the last day: September complete


def test_exclusion_log(toy):
    ex = toy.execute("select step, rows_after from int_exclusions order by step").df()
    assert ex.rows_after.tolist() == [9, 6, 6, 3, 4, 3, 4, 4]


def test_fulfilment_funnel_overall(toy):
    f = row(toy, "select * from mart_fulfilment_funnel where dimension = 'overall'")
    assert (f.n_purchased, f.n_approved, f.n_shipped, f.n_delivered, f.n_reviewed) == (9, 8, 7, 6, 3)
    assert f.conv_purchased_to_delivered == pytest.approx(6 / 9)
    assert f.conv_delivered_to_reviewed == pytest.approx(3 / 6)
    assert f.conv_approved_to_shipped == pytest.approx(7 / 8)
    # Approval delays in hours: 0.5, 1/6, 1, 1, 0.5, 1, 1, 0.5 -> median 0.75
    assert f.median_h_purchase_to_approve == pytest.approx(0.75)


def test_fulfilment_funnel_by_month(toy):
    f = toy.execute("select dimension_value, n_purchased, n_delivered from mart_fulfilment_funnel "
                    "where dimension = 'month'").df().set_index("dimension_value")
    assert f.loc["2017-01"].tolist() == [2, 1]      # o1 delivered, o3 canceled
    assert f.loc["2017-02"].tolist() == [4, 2]      # o4, o5, o6, o9
    assert f.n_purchased.sum() == 9


def test_seller_funnel(toy):
    s = toy.execute("select * from mart_seller_funnel").df()
    ov = s[s.dimension == "overall"].iloc[0]
    assert (ov.n_leads, ov.n_closed, ov.n_first_sale, ov.n_first_sale_observed, ov.n_still_selling) == (3, 2, 1, 1, 1)
    assert ov.conv_lead_to_closed == pytest.approx(2 / 3)
    assert ov.conv_closed_to_first_sale == pytest.approx(0.5)
    assert ov.median_days_lead_to_close == pytest.approx(10.5)       # 4 and 17 days
    assert ov.median_days_close_to_first_sale == pytest.approx(5)
    origin = s[s.dimension == "lead_origin"].set_index("dimension_value")
    assert origin.loc["unknown", "n_leads"] == 1                     # NULL origin labelled, not dropped
    assert origin.loc["paid_search", "n_first_sale"] == 0
    seg = s[s.dimension == "business_segment"].set_index("dimension_value")
    assert seg.n_leads.isna().all()                                  # leads have no segment
    assert seg.loc["home", "n_first_sale"] == 1 and seg.loc["toys", "n_first_sale"] == 0
