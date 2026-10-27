-- Zip prefixes repeat many times with slightly different coordinates.
-- Not used in the analysis; profiled only.
create or replace view stg_geolocation as
select
    geolocation_zip_code_prefix          as zip_prefix,
    try_cast(geolocation_lat as double)  as lat,
    try_cast(geolocation_lng as double)  as lng,
    geolocation_city                     as city,
    upper(geolocation_state)             as state
from raw_geolocation;
