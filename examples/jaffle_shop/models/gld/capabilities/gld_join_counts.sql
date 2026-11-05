{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH "__extra_cross_rows" AS (
  SELECT
    'cross' AS "join_type",
    COUNT(*) AS "row_count"
  FROM {{ ref('slv_orders') }} AS "o"
  CROSS JOIN {{ ref('slv_customers') }} AS "c"
), "__extra_full_rows" AS (
  SELECT
    'full' AS "join_type",
    COUNT(*) AS "row_count"
  FROM {{ ref('slv_orders') }} AS "o"
  FULL JOIN {{ ref('slv_customers') }} AS "c"
    ON o.customer_id = c.customer_id
), "__extra_inner_rows" AS (
  SELECT
    'inner' AS "join_type",
    COUNT(*) AS "row_count"
  FROM {{ ref('slv_orders') }} AS "o"
  INNER JOIN {{ ref('slv_customers') }} AS "c"
    ON o.customer_id = c.customer_id
), "__extra_left_rows" AS (
  SELECT
    'left' AS "join_type",
    COUNT(*) AS "row_count"
  FROM {{ ref('slv_orders') }} AS "o"
  LEFT JOIN {{ ref('slv_customers') }} AS "c"
    ON o.customer_id = c.customer_id
), "__extra_right_rows" AS (
  SELECT
    'right' AS "join_type",
    COUNT(*) AS "row_count"
  FROM {{ ref('slv_orders') }} AS "o"
  RIGHT JOIN {{ ref('slv_customers') }} AS "c"
    ON o.customer_id = c.customer_id
)
SELECT
  i.join_type,
  i.row_count
FROM "__extra_inner_rows" AS i
UNION ALL
SELECT
  l.join_type,
  l.row_count
FROM "__extra_left_rows" AS l
UNION ALL
SELECT
  r.join_type,
  r.row_count
FROM "__extra_right_rows" AS r
UNION ALL
SELECT
  f.join_type,
  f.row_count
FROM "__extra_full_rows" AS f
UNION ALL
SELECT
  c.join_type,
  c.row_count
FROM "__extra_cross_rows" AS c
