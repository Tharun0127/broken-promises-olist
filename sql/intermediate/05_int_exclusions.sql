-- Exclusion log: every row dropped on the way to each analysis sample.
create or replace table int_exclusions as
with counts as (
    select
        (select count(*) from stg_orders)                                     as all_orders,
        (select count(*) from stg_orders where order_status = 'delivered')    as status_delivered,
        (select count(*) from int_delivered_orders)                           as delivered_with_date,
        (select count(*) from int_delivered_orders where has_review)          as with_review,
        (select count(*) from int_delivered_orders where is_first_order)      as first_orders,
        (select count(*) from int_delivered_orders
          where is_first_order and repeat_window_observed)                    as first_orders_observed,
        (select count(distinct customer_unique_id) from int_delivered_orders) as customers,
        (select count(*) from (
            select customer_unique_id
            from int_delivered_orders
            group by 1
            having min(purchase_date) >= (select cohort_start from params)
        ))                                                                    as cohort_customers
)
select step, sample, description, rows_before, rows_after,
       rows_before - rows_after as rows_removed
from (
    select 1 as step, 'Grain' as sample, 'All orders in the raw data' as description,
           null::bigint as rows_before, all_orders as rows_after from counts
    union all
    select 2, 'Grain', 'Remove orders whose status is not delivered',
           all_orders, status_delivered from counts
    union all
    select 3, 'Grain', 'Remove delivered orders with no delivery timestamp',
           status_delivered, delivered_with_date from counts
    union all
    select 4, 'Reviews', 'Review outcomes: remove delivered orders with no review',
           delivered_with_date, with_review from counts
    union all
    select 5, 'Repeat', 'Repeat outcome: keep only each customer''s first delivered order',
           delivered_with_date, first_orders from counts
    union all
    select 6, 'Repeat', 'Repeat outcome: remove first orders without a full repeat window before data end',
           first_orders, first_orders_observed from counts
    union all
    select 7, 'Cohorts', 'Customers (customer_unique_id) with at least one delivered order',
           null, customers from counts
    union all
    select 8, 'Cohorts', 'Remove customers whose first purchase is before the cohort start',
           customers, cohort_customers from counts
)
order by step;
