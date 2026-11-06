SELECT
    id AS customer_id,
    TRIM(first_name) AS first_name,
    TRIM(last_name) AS last_name
FROM {{ source('shop', 'customers') }}
