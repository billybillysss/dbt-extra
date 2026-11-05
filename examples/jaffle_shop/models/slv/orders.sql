{{ config(materialized='view') }}

select
    order_id,
    customer_id,
    cast(amount as decimal(12, 2)) as amount
from {{ ref('demo_raw_orders') }}
where status = 'completed'
