select customer_id, {{ round_money('revenue') }} as revenue
from {{ ref('customer_revenue') }}
