-- Customer cohort retention triangle, long format.
-- Cohort = month of a customer's first delivered purchase.
-- Cell (cohort, k) = share of the cohort that purchased in month k after it.
-- Cells the data cannot see yet (right censoring) are NULL, not zero.
create or replace table mart_customer_cohorts as
with customer_months as (
    -- Date bucketing: each purchase becomes the month it happened in.
    select distinct
        customer_unique_id,
        date_trunc('month', purchase_date)::date as activity_month
    from int_delivered_orders
),

with_cohort as (
    -- Window function: the first month per customer is their cohort.
    select
        customer_unique_id,
        activity_month,
        min(activity_month) over (partition by customer_unique_id) as cohort_month
    from customer_months
),

indexed as (
    select
        *,
        date_diff('month', cohort_month, activity_month) as month_number
    from with_cohort
),

cohort_size as (
    select cohort_month, count(*) as cohort_customers
    from indexed
    where month_number = 0
      and cohort_month >= (select cohort_start from params)
      and cohort_month <= (select last_complete_month from int_data_window)
    group by cohort_month
),

grid as (
    -- Every cohort x month cell up to the last complete month, so that months
    -- with zero buyers show 0 and months not yet observed are explicitly NULL.
    select
        c.cohort_month,
        c.cohort_customers,
        k.month_number,
        c.cohort_month + to_months(k.month_number::integer) <= (select last_complete_month from int_data_window)
            as is_observed
    from cohort_size c
    cross join (
        select unnest(generate_series(0, date_diff('month',
            (select cohort_start from params),
            (select last_complete_month from int_data_window)))) as month_number
    ) k
),

active as (
    select cohort_month, month_number, count(*) as active_customers
    from indexed
    group by cohort_month, month_number
),

first_repeat as (
    -- Month of each customer's first repeat (a purchase on a later day).
    select
        cohort_month,
        date_diff('month', cohort_month, date_trunc('month', first_repeat_date)::date) as repeat_month_number
    from mart_customers
    where first_repeat_date is not null
),

cumulative_repeat as (
    -- Running count of customers who have repeated by month k.
    select
        g.cohort_month,
        g.month_number,
        count(r.cohort_month) as repeated_by_month
    from grid g
    left join first_repeat r
      on r.cohort_month = g.cohort_month
     and r.repeat_month_number <= g.month_number
    group by g.cohort_month, g.month_number
)

select
    g.cohort_month,
    g.month_number,
    g.cohort_customers,
    g.is_observed,
    case when g.is_observed then coalesce(a.active_customers, 0) end          as active_customers,
    case when g.is_observed then coalesce(a.active_customers, 0) / g.cohort_customers end
                                                                               as retention,
    case when g.is_observed then cr.repeated_by_month end                     as repeated_by_month,
    case when g.is_observed then cr.repeated_by_month / g.cohort_customers end as cumulative_repeat_rate
from grid g
left join active a using (cohort_month, month_number)
left join cumulative_repeat cr using (cohort_month, month_number)
order by g.cohort_month, g.month_number;
