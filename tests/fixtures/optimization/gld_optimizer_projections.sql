{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH projected AS (
    SELECT o.order_id, o.customer_id, o.status AS unused_status
    FROM {{ ref('slv_orders') }} AS o
), normalized AS (
    SELECT p.order_id, p.customer_id FROM projected AS p
), unused AS (
    SELECT 9 AS ignored
)
SELECT n.order_id, n.customer_id
FROM normalized AS n
WHERE n.customer_id > 0 AND TRUE
