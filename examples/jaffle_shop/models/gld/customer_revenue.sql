{{ config(materialized='table', tags=['finance']) }}

with order_totals as (
    select customer_id, sum(amount) as revenue, count(*) as order_count
    from {{ ref('orders') }}
    group by customer_id
)
select customer_id, revenue + 0 as revenue, order_count
from order_totals
