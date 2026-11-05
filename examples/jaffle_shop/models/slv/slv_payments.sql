{{ config(materialized='view', meta={'domain': 'sales'}) }}

SELECT
  CAST(p.id AS BIGINT) AS "payment_id",
  p.order_id AS "order_id",
  p.payment_method AS "payment_method",
  CAST({{ round_money('p.amount / 100.0') }} AS DECIMAL(12, 2)) AS "amount"
FROM {{ ref('brz_payments') }} AS "p"
