-- One row per customer (customer_unique_id), built from delivered orders.
create or replace table mart_customers as
with first_order as (
    select *
    from int_delivered_orders
    where is_first_order
),
activity as (
    select
        customer_unique_id,
        count(*)                      as n_orders,
        count(distinct purchase_date) as n_purchase_days,
        sum(order_value)              as lifetime_value
    from int_delivered_orders
    group by customer_unique_id
)
select
    f.customer_unique_id,
    f.customer_state,
    f.purchase_date                              as first_purchase_date,
    date_trunc('month', f.purchase_date)::date   as cohort_month,
    a.n_orders,
    a.n_purchase_days,
    a.lifetime_value,
    -- Repeat customer = bought again on a later day, at any time in the data.
    a.n_purchase_days > 1                        as is_repeat_customer,
    f.next_purchase_date                         as first_repeat_date,
    date_diff('day', f.purchase_date, f.next_purchase_date) as days_to_first_repeat,
    f.repeat_window_observed,
    f.repeat_in_window,
    f.is_late                                    as first_order_late,
    f.days_late                                  as first_order_days_late
from first_order f
join activity a using (customer_unique_id);
