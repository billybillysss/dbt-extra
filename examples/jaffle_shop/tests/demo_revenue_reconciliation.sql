-- Keep the completed-only walkthrough independent from the classic seeds.
with checks as (
    select 'completed_order_count' as check_name,
        (select count(*) from {{ ref('orders') }}) as actual,
        3 as expected
    union all
    select 'customer_count',
        (select count(*) from {{ ref('customer_revenue') }}),
        2
    union all
    select 'customer_10_revenue',
        (select revenue from {{ ref('customer_revenue') }} where customer_id = 10),
        35.50
    union all
    select 'customer_20_revenue',
        (select revenue from {{ ref('customer_revenue') }} where customer_id = 20),
        12.25
    union all
    select 'macro_customer_count',
        (select count(*) from {{ ref('macro_revenue') }}),
        2
    union all
    select 'macro_revenue_total',
        (select sum(revenue) from {{ ref('macro_revenue') }}),
        47.75
)
select * from checks where actual is distinct from expected
