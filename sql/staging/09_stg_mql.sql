-- Marketing qualified leads: sellers who showed interest in joining Olist.
create or replace view stg_mql as
select
    mql_id,
    try_cast(first_contact_date as date) as first_contact_date,
    landing_page_id,
    coalesce(origin, 'unknown')          as lead_origin
from raw_mql;
