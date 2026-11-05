{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT eligible.order_id, eligible.customer_id
FROM (
    SELECT DISTINCT o.order_id, o.customer_id
    FROM {{ ref('slv_orders') }} AS o
) AS eligible
WHERE eligible.customer_id > 10 AND TRUE
