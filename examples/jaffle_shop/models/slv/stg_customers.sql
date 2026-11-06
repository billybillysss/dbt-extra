SELECT
    id AS customer_id,
    TRIM(first_name) AS first_name,
    last_name
FROM {{ source('jaffle_shop', 'customers') }}
