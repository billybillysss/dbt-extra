{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT *
FROM {{ ref('slv_orders') }}
WHERE TRUE
