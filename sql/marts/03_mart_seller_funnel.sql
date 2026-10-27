-- Seller acquisition funnel: lead > closed deal > first sale > still selling
-- 90 days after the first sale. One row per (dimension, value).
create or replace table mart_seller_sales as
-- Every delivered sale per seller. A seller sells on an order if any item is theirs.
select distinct
    i.seller_id,
    d.order_id,
    d.purchase_date
from stg_order_items i
join int_delivered_orders d using (order_id);

create or replace table mart_seller_funnel as
with seller_activity as (
    select
        seller_id,
        min(purchase_date) as first_sale_date,
        max(purchase_date) as last_sale_date
    from mart_seller_sales
    group by seller_id
),

still_selling as (
    -- A seller is still selling if any sale falls on or after first sale + 90 days.
    select
        a.seller_id,
        bool_or(s.purchase_date >= a.first_sale_date + (select seller_active_days from params))
            as sold_after_window
    from seller_activity a
    join mart_seller_sales s using (seller_id)
    group by a.seller_id
),

leads as (
    -- One row per lead with how far it got. Unclosed leads have no segment.
    select
        m.mql_id,
        m.lead_origin,
        coalesce(d.business_segment, 'not_closed')        as business_segment,
        m.first_contact_date,
        d.won_at,
        a.first_sale_date,
        d.mql_id is not null                              as is_closed,
        a.seller_id is not null                           as has_first_sale,
        -- Right censoring: is the 90-day window fully inside the data?
        a.first_sale_date + (select seller_active_days from params)
            <= (select data_end from int_data_window)     as window_observed,
        coalesce(st.sold_after_window, false)             as sold_after_window
    from stg_mql m
    left join stg_closed_deals d using (mql_id)
    left join seller_activity a on a.seller_id = d.seller_id
    left join still_selling st on st.seller_id = d.seller_id
),

aggregated as (
    select
        case
            when grouping(lead_origin) = 0 then 'lead_origin'
            when grouping(business_segment) = 0 then 'business_segment'
            else 'overall'
        end                                                          as dimension,
        coalesce(lead_origin, business_segment, 'all')               as dimension_value,
        count(*)                                                     as n_leads,
        count(*) filter (where is_closed)                            as n_closed,
        count(*) filter (where has_first_sale)                       as n_first_sale,
        count(*) filter (where has_first_sale and window_observed)   as n_first_sale_observed,
        count(*) filter (where has_first_sale and not window_observed) as n_censored,
        count(*) filter (where has_first_sale and window_observed and sold_after_window)
                                                                     as n_still_selling,
        median(date_diff('day', first_contact_date, won_at::date)) filter (where is_closed)
                                                                     as median_days_lead_to_close,
        median(date_diff('day', won_at::date, first_sale_date)) filter (where has_first_sale)
                                                                     as median_days_close_to_first_sale
    from leads
    group by grouping sets ((), (lead_origin), (business_segment))
)

select
    dimension,
    dimension_value,
    -- Segment exists only for closed deals, so lead counts by segment are not defined.
    case when dimension = 'business_segment' then null else n_leads end as n_leads,
    n_closed,
    n_first_sale,
    n_first_sale_observed,
    n_censored,
    n_still_selling,
    case when dimension = 'business_segment' then null
         else n_closed / n_leads end                                   as conv_lead_to_closed,
    n_first_sale / nullif(n_closed, 0)                                 as conv_closed_to_first_sale,
    -- Only sellers with the full window observed are in the denominator.
    n_still_selling / nullif(n_first_sale_observed, 0)                 as conv_first_sale_to_still_selling,
    median_days_lead_to_close,
    median_days_close_to_first_sale
from aggregated
where not (dimension = 'business_segment' and dimension_value = 'not_closed')
order by dimension, n_closed desc, dimension_value;
