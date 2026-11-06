WITH ordering_customers AS (
    SELECT user_id AS customer_id
    FROM {{ source('shop', 'orders') }}
    GROUP BY user_id
)
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    CASE
        WHEN o.customer_id IS NOT NULL THEN TRUE
        ELSE FALSE
    END AS has_orders
FROM {{ ref('stg_customers') }} AS c
LEFT JOIN ordering_customers AS o
    ON c.customer_id = o.customer_id
