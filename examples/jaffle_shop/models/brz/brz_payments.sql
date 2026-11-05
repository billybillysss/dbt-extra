{{ config(materialized='view', meta={'domain': 'sales'}) }}

SELECT
  p.id AS "id",
  p.order_id AS "order_id",
  p.payment_method AS "payment_method",
  p.amount AS "amount"
FROM {{ source('jaffle_shop', 'payments') }} AS "p"
