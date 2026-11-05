{{ config(materialized='view', meta={'domain': 'sales'}) }}

SELECT
  CAST(c.id AS BIGINT) AS "customer_id",
  TRIM(c.first_name) AS "first_name",
  TRIM(c.last_name) AS "last_name"
FROM {{ ref('brz_customers') }} AS "c"
