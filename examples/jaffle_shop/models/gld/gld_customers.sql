{{ config(contract={'enforced': True}, materialized='table', meta={'owner': 'analytics', 'domain': 'sales'}) }}

WITH "__extra_customer_orders" AS (
  SELECT
    o.customer_id AS "customer_id",
    MIN(o.order_date) AS "first_order",
    MAX(o.order_date) AS "most_recent_order",
    COUNT(*) AS "number_of_orders",
    CAST(SUM(o.amount) AS DECIMAL(12, 2)) AS "customer_lifetime_value"
  FROM {{ ref('gld_orders') }} AS "o"
  GROUP BY
    o.customer_id
)
SELECT
  c.customer_id AS "customer_id",
  c.first_name AS "first_name",
  c.last_name AS "last_name",
  o.first_order AS "first_order",
  o.most_recent_order AS "most_recent_order",
  COALESCE(o.number_of_orders, CAST(0 AS BIGINT)) AS "number_of_orders",
  CAST(COALESCE(o.customer_lifetime_value, 0) AS DECIMAL(12, 2)) AS "customer_lifetime_value"
FROM {{ ref('slv_customers') }} AS "c"
LEFT JOIN "__extra_customer_orders" AS "o"
  ON c.customer_id = o.customer_id
