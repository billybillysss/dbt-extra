{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH payment_input AS (
  SELECT
    o.customer_id,
    o.order_id,
    o.amount,
    o.status AS unused_status
  FROM {{ ref('gld_orders') }} AS o
)
SELECT
  paid.customer_id
FROM (
  SELECT DISTINCT
    o.customer_id,
    o.order_id
  FROM payment_input AS o
  WHERE
    o.amount > 0
) AS paid
