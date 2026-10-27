-- Seller activity cohorts. Cohort = month of a seller's first delivered sale.
-- Cell (cohort, k) = share of the cohort's sellers with a sale in month k.
-- Same censoring rule as customers: unobserved cells are NULL.
create or replace table mart_seller_cohorts as
with seller_months as (
    select distinct
        seller_id,
        date_trunc('month', purchase_date)::date as activity_month
    from mart_seller_sales
),

with_cohort as (
    select
        seller_id,
        activity_month,
        min(activity_month) over (partition by seller_id) as cohort_month
    from seller_months
),

indexed as (
    select *, date_diff('month', cohort_month, activity_month) as month_number
    from with_cohort
),

cohort_size as (
    select cohort_month, count(*) as cohort_sellers
    from indexed
    where month_number = 0
      and cohort_month >= (select cohort_start from params)
      and cohort_month <= (select last_complete_month from int_data_window)
    group by cohort_month
),

grid as (
    select
        c.cohort_month,
        c.cohort_sellers,
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
    select cohort_month, month_number, count(*) as active_sellers
    from indexed
    group by cohort_month, month_number
)

select
    g.cohort_month,
    g.month_number,
    g.cohort_sellers,
    g.is_observed,
    case when g.is_observed then coalesce(a.active_sellers, 0) end               as active_sellers,
    case when g.is_observed then coalesce(a.active_sellers, 0) / g.cohort_sellers end as activity_rate
from grid g
left join active a using (cohort_month, month_number)
order by g.cohort_month, g.month_number;
