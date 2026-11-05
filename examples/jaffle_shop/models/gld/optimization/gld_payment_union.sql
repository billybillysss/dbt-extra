{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT
  p.order_id,
  p.amount
FROM {{ ref('slv_payments') }} AS p
WHERE
  p.payment_method = 'credit_card'
UNION ALL
SELECT
  p.order_id,
  p.amount
FROM {{ ref('slv_payments') }} AS p
WHERE
  p.payment_method <> 'credit_card'
