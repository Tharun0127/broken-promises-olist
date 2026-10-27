"""Known-answer tests for cohort retention and right censoring."""
import math

import pytest


def cells(con, table, value):
    df = con.execute(f"select cohort_month, month_number, is_observed, {value} from {table}").df()
    df["cohort"] = df.cohort_month.astype(str).str[:7]
    return df.set_index(["cohort", "month_number"])


def test_customer_table(toy):
    c = toy.execute("select * from mart_customers").df().set_index("customer_unique_id")
    assert set(c.index) == {"U1", "U2", "U4", "U6"}          # U3 and U5 never had a delivered order
    assert c.is_repeat_customer.to_dict() == {"U1": True, "U2": False, "U4": False, "U6": False}
    assert str(c.loc["U2", "first_purchase_date"].date()) == "2017-04-01"   # canceled o3 does not count
    assert c.is_repeat_customer.mean() == pytest.approx(0.25)
    observed = c[c.repeat_window_observed]
    assert set(observed.index) == {"U1", "U2", "U4"}          # U6 bought on the last day
    assert observed.repeat_in_window.mean() == pytest.approx(1 / 3)


def test_customer_cohort_triangle(toy):
    t = cells(toy, "mart_customer_cohorts", "cohort_customers, retention, cumulative_repeat_rate")
    assert t.loc[("2017-01", 0), "retention"] == 1.0
    assert t.loc[("2017-01", 1), "retention"] == 0.0           # observed and nobody bought
    assert t.loc[("2017-01", 2), "retention"] == 1.0           # U1 bought in March
    assert t.loc[("2017-01", 1), "cumulative_repeat_rate"] == 0.0
    assert t.loc[("2017-01", 2), "cumulative_repeat_rate"] == 1.0
    assert t.loc[("2017-02", 0), "cohort_customers"] == 1      # U4's same-day orders are one customer


def test_censored_cells_are_null_not_zero(toy):
    t = cells(toy, "mart_customer_cohorts", "retention")
    assert t.loc[("2017-01", 8), "is_observed"]                # September 2017 is complete
    assert not t.loc[("2017-02", 8), "is_observed"]            # October 2017 is beyond the data
    assert math.isnan(t.loc[("2017-02", 8), "retention"])
    assert t.loc[("2017-09", 0), "is_observed"]
    assert math.isnan(t.loc[("2017-09", 1), "retention"])


def test_seller_cohorts(toy):
    t = cells(toy, "mart_seller_cohorts", "cohort_sellers, activity_rate")
    # s1 and s2 both first sold in January 2017.
    assert t.loc[("2017-01", 0), "cohort_sellers"] == 2
    assert t.loc[("2017-01", 1), "activity_rate"] == 0.5       # s2 (February)
    assert t.loc[("2017-01", 3), "activity_rate"] == 0.5       # s1 (April)
    assert t.loc[("2017-01", 4), "activity_rate"] == 0.0


def test_curve_pools_only_observed_cells():
    import pandas as pd
    from src.cohorts import curve
    df = pd.DataFrame({
        "cohort_month": ["a", "a", "b", "b"], "month_number": [0, 1, 0, 1],
        "is_observed": [True, True, True, False],
        "active": [10, 2, 30, None], "size": [10, 10, 30, 30]})
    g = curve(df, "active", "size").set_index("month_number")
    # Month 1 uses only cohort a (b is censored): 2 / 10, not 2 / 40.
    assert g.loc[1, "rate"] == pytest.approx(0.2)
    assert g.loc[1, "n_cohorts"] == 1
