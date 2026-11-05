{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH customer_input AS (
  SELECT c.customer_id, c.first_name, c.last_name, c.number_of_orders,
    c.customer_lifetime_value, c.first_order AS unused_first_order
  FROM {{ ref('gld_customers') }} AS c
)
SELECT c.customer_id, c.first_name, c.last_name, c.number_of_orders, c.customer_lifetime_value
FROM customer_input AS c
