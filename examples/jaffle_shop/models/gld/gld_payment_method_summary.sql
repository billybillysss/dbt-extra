{{ config(materialized='view', meta={'owner': 'payments', 'domain': 'sales'}) }}

SELECT
  p.payment_method AS "payment_method",
  COUNT(*) AS "payment_count",
  COUNT(DISTINCT p.order_id) AS "paid_order_count",
  CAST(SUM(p.amount) AS DECIMAL(12, 2)) AS "payment_total"
FROM {{ ref('slv_payments') }} AS "p"
GROUP BY
  p.payment_method
