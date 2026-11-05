{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT a.customer_id, a.order_count, b.order_count AS repeated_order_count
FROM (
    SELECT o.customer_id, COUNT(*) AS order_count
    FROM {{ ref('slv_orders') }} AS o
    GROUP BY o.customer_id
) AS a
JOIN (
    SELECT o.customer_id, COUNT(*) AS order_count
    FROM {{ ref('slv_orders') }} AS o
    GROUP BY o.customer_id
) AS b ON a.customer_id = b.customer_id
