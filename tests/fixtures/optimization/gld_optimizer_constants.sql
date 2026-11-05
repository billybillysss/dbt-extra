{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT 100 / 100 AS currency_scale, 1 + 2 AS sample_value
