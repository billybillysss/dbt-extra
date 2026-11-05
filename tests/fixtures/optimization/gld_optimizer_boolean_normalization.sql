{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT o.order_id, o.customer_id
FROM {{ ref('slv_orders') }} AS o
WHERE (o.customer_id = 1 AND o.status = 'completed') OR o.customer_id = 2
