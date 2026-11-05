{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'sales'}) }}

SELECT
  o.order_date AS "order_date",
  o.status AS "status",
  COUNT(*) AS "order_count",
  CAST({{ round_money('SUM(o.amount)') }} AS DECIMAL(12, 2)) AS "payment_total"
FROM {{ ref('gld_orders') }} AS "o"
GROUP BY
  o.order_date,
  o.status
