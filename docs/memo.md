# Memo: late deliveries, reviews and repeat purchases

**To:** Olist operations and CX leads. **Data:** Olist orders 2016-09-04 to 2018-08-29.

## Answer

Late deliveries hurt reviews, but the damage comes from being several days late, not from missing the
date by one. Repeat purchases show no measurable loss.

- Late orders get far more 1-star reviews: 53.8% against 6.6% on time.
- Missing the promise by a day adds little on its own. Allowing for the trend, the jump at the promise date is
  -1.7 pp (95% CI -4.9 pp to +1.5 pp).
- The rate then climbs fast: 13.0% on day 1, 42.5% on day 3. Day 3 is when
  most late customers start getting the review survey before the parcel (70.2%).
- No detectable effect on repeat purchase (+0.1 pp, CI -2.0 pp to
  +2.2 pp). Only 2.0% of customers return within 180 days, so the worst
  case is R$ 2,554 of order value per quarter.

## Recommendations, ranked

**1. Test a proactive delay message.** Message customers the day after a missed date with a new date.
Randomise by customer, keep survey timing the same in both arms, and judge on the 1-star rate. Size:
820 late orders a quarter carrying R$ 149,463 of order value. Needs
1,245 orders per arm, about 5.7 months. Ranked first because it is cheap, targets the
days where the damage builds, and produces evidence the data cannot.

**2. Stop sending the review survey before the parcel arrives.** 576 orders a
quarter (R$ 106,092 of order value) were surveyed before delivery. Trigger the
survey on confirmed delivery. This makes reviews rate the product and the seller, not the wait. Its money value
cannot be computed here: the data has no link from reviews to later sales.

**3. Cut delays of three days or more, starting in the highest-risk states.** Orders 3 or more days late carried
R$ 118,724 of order value a quarter. AL, MA, SE, PI, CE are late 15.7%
of the time against 6.8% nationally, but hold only 7.7%
of late orders, so this is a targeted fix, not the main lever. Ranked last because it costs the most to act on.

## Limitations

- The causal estimate is local to the promise date. Orders a week late are described, not causally estimated.
- The density and covariate checks partly fail. Orders just on time and just late differ a little.
- Money is customer order value. Olist's commission is not in the data.
- Data is from 2016 to 2018. Volumes and delivery performance today will differ.
