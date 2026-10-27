create or replace view stg_category_translation as
select
    product_category_name         as category_pt,
    product_category_name_english as category_en
from raw_category_translation;
