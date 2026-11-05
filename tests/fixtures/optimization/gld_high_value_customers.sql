{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT candidate_order.order_id, candidate_order.customer_id, candidate_order.amount,
  (SELECT AVG(benchmark_order.amount)
   FROM {{ ref('gld_orders') }} AS benchmark_order) AS average_order_amount
FROM {{ ref('gld_orders') }} AS candidate_order
WHERE candidate_order.amount > (
  SELECT AVG(benchmark_order.amount)
  FROM {{ ref('gld_orders') }} AS benchmark_order
)
AND EXISTS(
  SELECT 1
  FROM {{ ref('slv_payments') }} AS eligible_payment
  WHERE eligible_payment.order_id = candidate_order.order_id
    AND eligible_payment.payment_method = 'credit_card'
)
