{{ config(materialized='view', meta={'domain': 'sales'}) }}

SELECT
  c.id AS "id",
  c.first_name AS "first_name",
  c.last_name AS "last_name"
FROM {{ source('jaffle_shop', 'customers') }} AS "c"
