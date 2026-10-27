-- One row per delivered order with the running variable, outcomes and
-- pre-treatment covariates for the regression discontinuity.
create or replace table mart_promise_gap as
with base as (
    select *
    from int_delivered_orders
)
select
    order_id,
    customer_unique_id,
    -- Running variable: whole days delivered after the promised date.
    days_late,
    is_late,
    -- Outcomes. Review outcomes exist only when a review exists.
    has_review,
    review_score,
    case when has_review then is_one_star::int end           as one_star,
    review_before_delivery,
    -- Repeat outcome: first orders with a full window only, otherwise NULL.
    case when is_first_order and repeat_window_observed
         then repeat_in_window::int end                       as repeat_180,
    case when is_first_order and repeat_window_observed
         then repeat_value_in_window end                      as repeat_value_180,
    is_first_order,
    -- Covariates fixed before delivery happens (used for balance checks).
    items_value,
    freight_value,
    order_value,
    n_items,
    promised_days,
    category_en,
    customer_state,
    purchase_month,
    purchase_date
from base;
