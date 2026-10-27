-- One row per order with item totals and a single category and seller.
-- An order can hold several products; the category and seller of the most
-- expensive item represent the order (ties go to the lowest item number).
create or replace table int_order_items_summary as
with items as (
    select
        i.*,
        coalesce(p.category_pt, 'unknown')                as category_pt,
        -- Two categories have no English translation; fall back to the Portuguese name.
        coalesce(t.category_en, p.category_pt, 'unknown') as category_en
    from stg_order_items i
    left join stg_products p using (product_id)
    left join stg_category_translation t on t.category_pt = p.category_pt
),
ranked as (
    select
        *,
        row_number() over (partition by order_id order by price desc, order_item_id) as price_rank
    from items
),
totals as (
    select
        order_id,
        count(*)                  as n_items,
        count(distinct seller_id) as n_sellers,
        sum(price)                as items_value,
        sum(freight_value)        as freight_value
    from items
    group by order_id
)
select
    t.*,
    r.seller_id as main_seller_id,
    r.category_pt,
    r.category_en
from totals t
join ranked r on r.order_id = t.order_id and r.price_rank = 1;
