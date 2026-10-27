-- Order fulfilment funnel: purchased > approved > shipped > delivered > reviewed.
-- One row per (dimension, value). GROUPING SETS produces the overall row,
-- the by-month rows and the by-category rows in a single pass.
create or replace table mart_fulfilment_funnel as
with stages as (
    -- Stages are cumulative: reaching a later stage implies the earlier ones.
    -- 14 delivered orders have no approval time but were clearly approved.
    select
        order_id,
        purchase_month,
        category_en,
        purchased_at,
        approved_at,
        shipped_at,
        delivered_at,
        review_answered_at,
        is_delivered                                           as reached_delivered,
        is_delivered or shipped_at is not null                 as reached_shipped,
        is_delivered or shipped_at is not null
            or approved_at is not null                         as reached_approved,
        is_delivered and review_id is not null                 as reached_reviewed
    from int_orders
),

durations as (
    -- Hours between consecutive stages, only when both timestamps exist.
    select
        *,
        date_diff('second', purchased_at, approved_at) / 3600.0  as h_purchase_to_approve,
        date_diff('second', approved_at, shipped_at) / 3600.0    as h_approve_to_ship,
        date_diff('second', shipped_at, delivered_at) / 3600.0   as h_ship_to_deliver,
        -- Can be negative: many late orders are reviewed before they arrive.
        date_diff('second', delivered_at, review_answered_at) / 3600.0 as h_deliver_to_review
    from stages
),

aggregated as (
    select
        case
            when grouping(purchase_month) = 0 then 'month'
            when grouping(category_en) = 0 then 'category'
            else 'overall'
        end                                                     as dimension,
        coalesce(strftime(purchase_month, '%Y-%m'), category_en, 'all') as dimension_value,
        count(*)                                                as n_purchased,
        count(*) filter (where reached_approved)                as n_approved,
        count(*) filter (where reached_shipped)                 as n_shipped,
        count(*) filter (where reached_delivered)               as n_delivered,
        count(*) filter (where reached_reviewed)                as n_reviewed,
        median(h_purchase_to_approve) filter (where reached_approved)  as median_h_purchase_to_approve,
        median(h_approve_to_ship)     filter (where reached_shipped)   as median_h_approve_to_ship,
        median(h_ship_to_deliver)     filter (where reached_delivered) as median_h_ship_to_deliver,
        median(h_deliver_to_review)   filter (where reached_reviewed)  as median_h_deliver_to_review
    from durations
    group by grouping sets ((), (purchase_month), (category_en))
)

select
    *,
    -- Step conversion: share of the previous stage that reached this one.
    n_approved  / n_purchased                  as conv_purchased_to_approved,
    n_shipped   / nullif(n_approved, 0)        as conv_approved_to_shipped,
    n_delivered / nullif(n_shipped, 0)         as conv_shipped_to_delivered,
    n_reviewed  / nullif(n_delivered, 0)       as conv_delivered_to_reviewed,
    -- End-to-end conversion from purchase.
    n_delivered / n_purchased                  as conv_purchased_to_delivered,
    n_reviewed  / n_purchased                  as conv_purchased_to_reviewed
from aggregated
order by dimension, dimension_value;
