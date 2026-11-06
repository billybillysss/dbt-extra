SELECT
    customer_id,
    first_name AS customer_name,
    last_name,
    has_orders
FROM {{ ref('customer_details') }}
