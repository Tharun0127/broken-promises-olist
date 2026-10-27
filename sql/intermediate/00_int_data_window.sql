-- The observation window. Every censoring rule in the project reads from here.
-- data_end is the last purchase among delivered orders. Later orders exist
-- (a handful in Sep/Oct 2018) but none were delivered, so they are not usable.
create or replace table int_data_window as
with bounds as (
    select max(purchased_at)::date as data_end
    from stg_orders
    where order_status = 'delivered'
)
select
    data_end,
    -- A month counts as observed only if every day of it is inside the data.
    case when data_end = last_day(data_end)
         then date_trunc('month', data_end)
         else date_trunc('month', data_end) - interval 1 month
    end::date as last_complete_month
from bounds;
