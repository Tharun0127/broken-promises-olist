-- One review per order. 547 orders have several reviews; keep the latest
-- answered one because it reflects the customer's final opinion.
create or replace table int_order_review as
with ranked as (
    select
        *,
        row_number() over (
            partition by order_id
            order by review_answered_at desc, review_id   -- review_id breaks ties deterministically
        ) as rn
    from stg_order_reviews
)
select order_id, review_id, review_score, review_sent_date, review_answered_at
from ranked
where rn = 1;
