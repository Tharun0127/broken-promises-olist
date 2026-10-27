-- One row per order. Raw text is cast to proper types here and nowhere else.
-- try_cast turns malformed values into NULL instead of failing the build.
create or replace view stg_orders as
select
    order_id,
    customer_id,
    order_status,
    try_cast(order_purchase_timestamp      as timestamp) as purchased_at,
    try_cast(order_approved_at             as timestamp) as approved_at,
    try_cast(order_delivered_carrier_date  as timestamp) as shipped_at,
    try_cast(order_delivered_customer_date as timestamp) as delivered_at,
    -- The estimate is a calendar date (time is always 00:00), so keep it as a date.
    cast(try_cast(order_estimated_delivery_date as timestamp) as date) as estimated_delivery_date
from raw_orders;
