-- customer_id is created per order; customer_unique_id identifies the person.
-- Retention work must use customer_unique_id (see docs/DECISIONS.md).
create or replace view stg_customers as
select
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix as customer_zip_prefix,
    customer_city,
    upper(customer_state)    as customer_state
from raw_customers;
