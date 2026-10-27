-- Source column names are misspelled ("lenght"); fixed here.
create or replace view stg_products as
select
    product_id,
    product_category_name                       as category_pt,
    try_cast(product_name_lenght as integer)        as name_length,
    try_cast(product_description_lenght as integer) as description_length,
    try_cast(product_photos_qty as integer)     as photos_qty,
    try_cast(product_weight_g as integer)       as weight_g,
    try_cast(product_length_cm as integer)      as length_cm,
    try_cast(product_height_cm as integer)      as height_cm,
    try_cast(product_width_cm as integer)       as width_cm
from raw_products;
