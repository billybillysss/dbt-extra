{{ config(materialized='view', meta={'domain': 'sales'}) }}

SELECT
  CAST(o.id AS BIGINT) AS "order_id",
  CAST(o.user_id AS BIGINT) AS "customer_id",
  CAST(o.order_date AS DATE) AS "order_date",
  LOWER(TRIM(o.status)) AS "status"
FROM {{ ref('brz_orders') }} AS "o"
