{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

SELECT
  c.customer_id AS "customer_id",
  {{ hash_relation_attributes(ref('slv_customers'), table_alias='c', exclude=['customer_id']) }} AS "attribute_hash"
FROM {{ ref('slv_customers') }} AS "c"
