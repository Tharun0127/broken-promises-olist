-- One row per review. A few orders have more than one review; the
-- intermediate layer keeps one per order.
create or replace view stg_order_reviews as
select
    review_id,
    order_id,
    try_cast(review_score as integer)                         as review_score,
    review_comment_title                                      as review_title,
    review_comment_message                                    as review_message,
    -- Creation date = the day Olist sent the satisfaction survey.
    cast(try_cast(review_creation_date as timestamp) as date) as review_sent_date,
    try_cast(review_answer_timestamp as timestamp)            as review_answered_at
from raw_order_reviews;
