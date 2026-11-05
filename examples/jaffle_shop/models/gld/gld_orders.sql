{{ config(contract={'enforced': True}, materialized='table', meta={'owner': 'analytics', 'domain': 'sales'}) }}

WITH "__extra_order_payments" AS (
  SELECT
    p.order_id AS "order_id",
    CAST(SUM(p.amount) AS DECIMAL(12, 2)) AS "amount",
    CAST(SUM(CASE WHEN p.payment_method = 'credit_card' THEN p.amount ELSE 0 END) AS DECIMAL(12, 2)) AS "credit_card_amount",
    COUNT(*) AS "payment_count"
  FROM {{ ref('slv_payments') }} AS "p"
  GROUP BY
    p.order_id
)
SELECT
  o.order_id AS "order_id",
  o.customer_id AS "customer_id",
  o.order_date AS "order_date",
  o.status AS "status",
  CAST(COALESCE(p.amount, 0) AS DECIMAL(12, 2)) AS "amount",
  CAST(COALESCE(p.credit_card_amount, 0) AS DECIMAL(12, 2)) AS "credit_card_amount",
  COALESCE(p.payment_count, CAST(0 AS BIGINT)) AS "payment_count"
FROM {{ ref('slv_orders') }} AS "o"
LEFT JOIN "__extra_order_payments" AS "p"
  ON o.order_id = p.order_id
