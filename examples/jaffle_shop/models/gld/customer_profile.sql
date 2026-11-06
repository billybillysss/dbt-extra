SELECT
    customer_id,
    first_name AS customer_name,
    last_name
FROM {{ ref('customer_details') }}
