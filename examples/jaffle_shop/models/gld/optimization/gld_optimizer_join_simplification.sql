{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT a.order_id, b.order_id AS peer_order_id, c.order_id AS matched_order_id
FROM {{ ref('slv_orders') }} AS a
CROSS JOIN {{ ref('slv_orders') }} AS b
JOIN {{ ref('slv_orders') }} AS c
    ON a.customer_id = c.customer_id AND b.customer_id = c.customer_id
