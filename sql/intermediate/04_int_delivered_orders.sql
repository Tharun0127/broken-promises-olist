-- THE ANALYSIS GRAIN: one row per delivered order.
-- Adds the promise gap (running variable), customer order sequence and the
-- repeat purchase outcome.
create or replace table int_delivered_orders as
with delivered as (
    select *
    from int_orders
    where is_delivered
),

-- Promise gap in whole days. The estimate is a date, so compare dates:
-- delivered on the promised day = 0 (on time), the day after = 1 (late).
gap as (
    select
        *,
        date_diff('day', estimated_delivery_date, delivered_at::date) as days_late,
        date_diff('day', purchase_date, estimated_delivery_date)      as promised_days,
        date_diff('day', purchase_date, delivered_at::date)           as actual_days
    from delivered
),

-- Order sequence per person. customer_unique_id, not customer_id, because
-- customer_id changes with every order.
sequenced as (
    select
        *,
        row_number() over (
            partition by customer_unique_id order by purchased_at, order_id
        ) as customer_order_number,
        lag(purchase_date) over (
            partition by customer_unique_id order by purchased_at, order_id
        ) as previous_purchase_date
    from gap
),

-- For each order, the customer's purchases on LATER calendar days.
-- Same-day orders are treated as one shopping session, not a repeat.
later_purchases as (
    select
        a.order_id,
        min(b.purchase_date) as next_purchase_date,
        sum(b.order_value) filter (
            where b.purchase_date <= a.purchase_date + (select repeat_window_days from params)
        ) as repeat_value_in_window
    from sequenced a
    join sequenced b
      on b.customer_unique_id = a.customer_unique_id
     and b.purchase_date > a.purchase_date
    group by a.order_id
),

window_end as (
    select
        s.order_id,
        s.purchase_date + (select repeat_window_days from params) as repeat_window_end
    from sequenced s
)

select
    s.*,
    s.days_late > 0                                             as is_late,
    s.review_id is not null                                     as has_review,
    (s.review_score = 1)                                        as is_one_star,
    -- Survey sent before the parcel arrived: the review cannot rate the product.
    (s.review_sent_date < s.delivered_at::date)                 as review_before_delivery,
    s.customer_order_number = 1                                 as is_first_order,
    date_diff('day', s.previous_purchase_date, s.purchase_date) as days_since_previous_order,
    l.next_purchase_date,
    coalesce(l.repeat_value_in_window, 0)                       as repeat_value_in_window,
    -- Right censoring: only orders with the full window observed get an outcome.
    w.repeat_window_end <= (select data_end from int_data_window) as repeat_window_observed,
    case
        when w.repeat_window_end > (select data_end from int_data_window) then null
        else coalesce(l.next_purchase_date <= w.repeat_window_end, false)
    end                                                         as repeat_in_window
from sequenced s
join window_end w using (order_id)
left join later_purchases l using (order_id);
