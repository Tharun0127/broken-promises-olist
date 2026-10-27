"""Section 6: translate the repeat purchase effect into money per quarter.

Loss per quarter = late first orders in the quarter
                 x effect of being late on 180-day repeat probability (pp, sign flipped)
                 x order value of the repeat purchases a repeater makes within 180 days.
Positive = money lost. Negative = the scenario implies late orders gain repeat value.
"""
import pandas as pd

from src import config

BASE_QUARTER = ("2018-04-01", "2018-07-01")   # 2018 Q2: the last complete quarter
BASE_QUARTER_LABEL = "2018 Q2"


def main(con, m):
    h = m["rd_bandwidth"]
    q0, q1 = BASE_QUARTER
    one = lambda s: con.execute(s).fetchone()[0]
    in_q = f"purchase_date >= date '{q0}' and purchase_date < date '{q1}'"

    vol = {
        "q_delivered_orders": one(f"select count(*) from mart_promise_gap where {in_q}"),
        "q_gmv": one(f"select sum(order_value) from mart_promise_gap where {in_q}"),
        "q_first_orders": one(f"select count(*) from mart_promise_gap where is_first_order and {in_q}"),
        "q_late_first_orders": one(
            f"select count(*) from mart_promise_gap where is_first_order and is_late and {in_q}"),
        "q_local_late_first_orders": one(
            f"select count(*) from mart_promise_gap where is_first_order and days_late between 1 and {h} and {in_q}"),
        "q_late_orders": one(f"select count(*) from mart_promise_gap where is_late and {in_q}"),
        "q_late_gmv": one(f"select sum(order_value) from mart_promise_gap where is_late and {in_q}"),
        "q_late3_orders": one(f"select count(*) from mart_promise_gap where days_late >= 3 and {in_q}"),
        "q_late3_gmv": one(f"select sum(order_value) from mart_promise_gap where days_late >= 3 and {in_q}"),
        "q_reviews_before_delivery": one(
            f"select count(*) from mart_promise_gap where review_before_delivery and {in_q}"),
        "q_reviews_before_delivery_gmv": one(
            f"select sum(order_value) from mart_promise_gap where review_before_delivery and {in_q}"),
        # Value a repeater brings back within 180 days, from all observed first orders.
        "repeat_value_per_repeater": one(
            "select avg(repeat_value_180) from mart_promise_gap where repeat_180 = 1"),
        "repeaters_observed": one("select count(*) from mart_promise_gap where repeat_180 = 1"),
    }
    vol["q_late_rate"] = vol["q_late_orders"] / vol["q_delivered_orders"]

    # Where lateness concentrates (all delivered orders).
    states = con.execute("""
        select customer_state, count(*) orders, avg(is_late::int) late_rate,
               sum(is_late::int) late_orders
        from mart_promise_gap group by 1 order by late_orders desc""").df()
    states["share_of_late"] = states.late_orders / states.late_orders.sum()
    states.to_csv(config.OUTPUTS / "late_by_state.csv", index=False)
    # High-risk states: late rate at least double the national rate.
    national = states.late_orders.sum() / states.orders.sum()
    risky = states[states.late_rate >= 2 * national].sort_values("late_rate", ascending=False)
    vol["risk_states"] = ", ".join(risky.customer_state)
    vol["risk_states_count"] = len(risky)
    vol["risk_states_share_of_late"] = float(risky.late_orders.sum() / states.late_orders.sum())
    vol["risk_states_share_of_orders"] = float(risky.orders.sum() / states.orders.sum())
    vol["risk_states_late_rate"] = float(risky.late_orders.sum() / risky.orders.sum())
    vol["national_late_rate"] = float(national)

    effects = {
        "low": m["rd_repeat_180_ci_high"],    # most favourable bound of the 95% CI
        "base": m["rd_repeat_180_estimate"],  # point estimate
        "high": m["rd_repeat_180_ci_low"],    # most harmful bound of the 95% CI
    }
    rows = []
    for scen, eff in effects.items():
        for scope, n in [("local", vol["q_local_late_first_orders"]), ("all_late", vol["q_late_first_orders"])]:
            lost_customers = -eff * n
            rows.append({"scenario": scen, "scope": scope, "effect_pp": 100 * eff, "late_first_orders": n,
                         "repeat_customers_lost": lost_customers,
                         "repeat_value_per_repeater": vol["repeat_value_per_repeater"],
                         "loss_per_quarter": lost_customers * vol["repeat_value_per_repeater"]})
    # Reference only: the naive late vs on-time gap. Not causal.
    eff = m["naive_repeat_180_diff"]
    rows.append({"scenario": "naive_reference", "scope": "all_late", "effect_pp": 100 * eff,
                 "late_first_orders": vol["q_late_first_orders"],
                 "repeat_customers_lost": -eff * vol["q_late_first_orders"],
                 "repeat_value_per_repeater": vol["repeat_value_per_repeater"],
                 "loss_per_quarter": -eff * vol["q_late_first_orders"] * vol["repeat_value_per_repeater"]})
    sizing = pd.DataFrame(rows)
    sizing.to_csv(config.OUTPUTS / "sizing.csv", index=False)

    out = {f"size_{k}": (float(v) if not isinstance(v, str) else v) for k, v in vol.items()}
    for r in rows:
        out[f"size_loss_{r['scenario']}_{r['scope']}"] = float(r["loss_per_quarter"])
        out[f"size_customers_{r['scenario']}_{r['scope']}"] = float(r["repeat_customers_lost"])
    out["size_high_all_late_share_of_q_gmv"] = out["size_loss_high_all_late"] / out["size_q_gmv"]
    write_assumptions(out, m)
    return out


def brl(v):
    return f"R$ {v:,.0f}"


def write_assumptions(s, m):
    h = m["rd_bandwidth"]
    text = f"""# Assumptions for the business sizing

Generated by `src/sizing.py`. Do not edit by hand. Money is in Brazilian reais (R$) of order value
(item price plus freight) paid by customers.

## Formula

Repeat value lost per quarter = late first orders in the quarter
x drop in the 180-day repeat probability caused by being late
x order value a repeat customer brings back within 180 days.

## Assumptions

1. **Base quarter is {BASE_QUARTER_LABEL}.** It is the last complete quarter. It had
   {s['size_q_delivered_orders']:,.0f} delivered orders, a late rate of {100 * s['size_q_late_rate']:.1f}% and
   {s['size_q_late_first_orders']:,.0f} late first orders. Quarters with a higher late rate would give a larger number.
2. **The effect is the RD estimate for repeat purchase within 180 days** (first orders, h = {h}):
   {100 * m['rd_repeat_180_estimate']:+.1f} pp, 95% CI {100 * m['rd_repeat_180_ci_low']:+.1f} pp to
   {100 * m['rd_repeat_180_ci_high']:+.1f} pp. Low, base and high use the favourable CI bound, the point
   estimate and the harmful CI bound.
3. **Scope "local" applies the effect only to first orders 1 to {h} days late** ({s['size_q_local_late_first_orders']:,.0f}
   in the quarter). This is where the RD identifies it.
4. **Scope "all late" applies the same effect to every late first order.** This is an extrapolation. Orders
   that are many days late probably lose more, which this cannot measure.
5. **Value per repeat customer is {brl(s['size_repeat_value_per_repeater'])}:** the average order value of all
   purchases made within 180 days by the {s['size_repeaters_observed']:,.0f} first-order customers who came back.
6. **Only the first-order effect is counted.** Repeat customers who get a late order are not included,
   because the RD sample is first orders only.
7. **The effect of a bad review on future sales is not counted.** The data has no link between a review
   and later demand for that seller or product, so it cannot be computed.
8. **Order value is not Olist revenue.** Olist earns a commission that is not in the data. Multiply by
   the commission rate to get Olist's share.

## Results per quarter

| Scenario | Effect | Local scope | All late scope |
|:--|--:|--:|--:|
| Low | {100 * m['rd_repeat_180_ci_high']:+.1f} pp | {brl(s['size_loss_low_local'])} | {brl(s['size_loss_low_all_late'])} |
| Base | {100 * m['rd_repeat_180_estimate']:+.1f} pp | {brl(s['size_loss_base_local'])} | {brl(s['size_loss_base_all_late'])} |
| High | {100 * m['rd_repeat_180_ci_low']:+.1f} pp | {brl(s['size_loss_high_local'])} | {brl(s['size_loss_high_all_late'])} |
| Naive gap (not causal, reference) | {100 * m['naive_repeat_180_diff']:+.1f} pp | | {brl(s['size_loss_naive_reference_all_late'])} |

A negative number means the scenario implies late orders gain repeat value. The low and base rows
are negative or close to zero because the estimate cannot be told apart from zero.

## Reading

Even the high scenario, applied to every late first order, is {brl(s['size_loss_high_all_late'])} per quarter.
That is {100 * s['size_high_all_late_share_of_q_gmv']:.2f}% of the quarter's order value ({brl(s['size_q_gmv'])}).
Repeat purchase is rare on Olist ({100 * m['repeat_rate_180d']:.1f}% within 180 days), so even a large relative
effect on it is a small amount of money. The bigger cost of late delivery is in reviews, which this data
cannot price.

## Exposure figures used in the recommendations ({BASE_QUARTER_LABEL})

- Order value of all late orders: {brl(s['size_q_late_gmv'])} ({s['size_q_late_orders']:,.0f} orders).
- Order value of orders 3 or more days late: {brl(s['size_q_late3_gmv'])} ({s['size_q_late3_orders']:,.0f} orders).
- Orders whose review survey was sent before delivery: {s['size_q_reviews_before_delivery']:,.0f}
  (order value {brl(s['size_q_reviews_before_delivery_gmv'])}).
- {s['size_risk_states_count']:.0f} states have a late rate at least double the national {100 * s['size_national_late_rate']:.1f}%
  ({s['size_risk_states']}). Together they have a late rate of {100 * s['size_risk_states_late_rate']:.1f}%, and hold
  {100 * s['size_risk_states_share_of_late']:.1f}% of late orders but only {100 * s['size_risk_states_share_of_orders']:.1f}% of all orders.
"""
    (config.DOCS / "assumptions.md").write_text(text, encoding="utf-8")
