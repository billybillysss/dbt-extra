{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH completed AS (
  SELECT
    o.customer_id
  FROM {{ ref('slv_orders') }} AS o
  WHERE
    o.status = 'completed'
), returned AS (
  SELECT
    o.customer_id
  FROM {{ ref('slv_orders') }} AS o
  WHERE
    o.status = 'returned'
), both_statuses AS (
  SELECT
    c.customer_id
  FROM completed AS c
  INTERSECT
  SELECT
    r.customer_id
  FROM returned AS r
), completed_only AS (
  SELECT
    c.customer_id
  FROM completed AS c
  EXCEPT
  SELECT
    r.customer_id
  FROM returned AS r
)
SELECT
  c.customer_id,
  'completed_only' AS cohort
FROM completed_only AS c
UNION
SELECT
  b.customer_id,
  'completed_and_returned' AS cohort
FROM both_statuses AS b
