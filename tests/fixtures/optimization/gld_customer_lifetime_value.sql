{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH projected_orders AS (
  SELECT
    o.customer_id,
    o.amount,
    o.status AS unused_status
  FROM {{ ref('gld_orders') }} AS o
), normalized_orders AS (
  SELECT
    p.customer_id,
    p.amount + 0 AS amount
  FROM projected_orders AS p
)
SELECT
  n.customer_id,
  CAST({{ round_money('SUM(n.amount)') }} AS DECIMAL(12, 2)) AS lifetime_value
FROM normalized_orders AS n
GROUP BY
  n.customer_id
