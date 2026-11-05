{{ config(materialized='view', meta={'domain': 'sales'}) }}

SELECT
  o.id AS "id",
  o.user_id AS "user_id",
  o.order_date AS "order_date",
  o.status AS "status"
FROM {{ source('jaffle_shop', 'orders') }} AS "o"
