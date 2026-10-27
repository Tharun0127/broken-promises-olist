-- A closed deal is a lead that signed up. seller_id links it to sales.
create or replace view stg_closed_deals as
select
    mql_id,
    seller_id,
    sdr_id,
    sr_id,
    try_cast(won_date as timestamp)                 as won_at,
    coalesce(business_segment, 'unknown')           as business_segment,
    lead_type,
    business_type,
    try_cast(declared_monthly_revenue as double)    as declared_monthly_revenue
from raw_closed_deals;
