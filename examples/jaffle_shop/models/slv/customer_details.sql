WITH customer_input AS (
    SELECT customer_id, first_name, last_name
    FROM {{ ref('stg_customers') }}
)
SELECT customer_id, first_name, last_name
FROM customer_input
