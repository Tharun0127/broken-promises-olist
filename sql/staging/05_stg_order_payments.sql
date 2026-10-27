create or replace view stg_order_payments as
select
    order_id,
    try_cast(payment_sequential as integer)   as payment_sequential,
    payment_type,
    try_cast(payment_installments as integer) as payment_installments,
    try_cast(payment_value as double)         as payment_value
from raw_order_payments;
