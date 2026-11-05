{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT
  o.order_id AS "order_id",
  {{ round_money('o.amount') }} AS "default_rounding",
  {{ round_money('o.amount', 1) }} AS "positional_rounding",
  {{ round_money('o.amount', decimal_places=1) }} AS "named_rounding",
  {{ round_money('o.amount', decimal_places=1) }} AS "alternate_named_rounding",
  {{ rounded_total(['COALESCE(o.amount, 0)', '1'], {'decimal_places': 1}) }} AS "rounded_with_fee"
FROM {{ ref('gld_orders') }} AS "o"
