-- Every order (all statuses), enriched. This feeds the fulfilment funnel,
-- which must see canceled and stuck orders too.
create or replace table int_orders as
select
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    c.customer_state,
    o.order_status,
    o.purchased_at,
    o.purchased_at::date                       as purchase_date,
    date_trunc('month', o.purchased_at)::date  as purchase_month,
    o.approved_at,
    o.shipped_at,
    o.delivered_at,
    o.estimated_delivery_date,
    coalesce(s.category_pt, 'no_items')        as category_pt,
    coalesce(s.category_en, 'no_items')        as category_en,
    s.main_seller_id,
    s.n_items,
    s.n_sellers,
    s.items_value,
    s.freight_value,
    s.items_value + s.freight_value            as order_value,
    r.review_id,
    r.review_score,
    r.review_sent_date,
    r.review_answered_at,
    -- The analysis grain: delivered status AND a delivery timestamp.
    (o.order_status = 'delivered' and o.delivered_at is not null) as is_delivered
from stg_orders o
join stg_customers c using (customer_id)
left join int_order_items_summary s using (order_id)
left join int_order_review r using (order_id);
