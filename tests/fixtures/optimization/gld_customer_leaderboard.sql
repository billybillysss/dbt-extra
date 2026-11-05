{{ config(materialized='table', meta={'owner': 'analytics', 'domain': 'demo'}) }}

WITH completed_orders AS (
  SELECT DISTINCT
    o.order_id,
    o.customer_id,
    {{ round_money('o.amount') }} AS amount
  FROM {{ ref('gld_orders') }} AS o
  WHERE
    o.status = 'completed' AND o.amount > 0
), customer_totals AS (
  SELECT
    c.customer_id,
    {{ round_money('SUM(c.amount)') }} AS revenue,
    COUNT(*) AS order_count,
    MAX(c.amount) AS largest_order
  FROM completed_orders AS c
  GROUP BY
    c.customer_id
  HAVING
    COUNT(*) >= 2
), customer_activity AS (
  SELECT
    a.customer_id,
    COUNT(*) AS all_order_count,
    SUM(CASE WHEN a.status = 'returned' THEN 1 ELSE 0 END) AS returned_order_count
  FROM {{ ref('slv_orders') }} AS a
  GROUP BY
    a.customer_id
), ranked AS (
  WITH scored AS (
    SELECT
      t.customer_id,
      t.revenue,
      t.order_count,
      ROUND(t.revenue / NULLIF(t.order_count, 0), 2) AS average_amount,
      ROW_NUMBER() OVER (ORDER BY t.revenue DESC, t.customer_id) AS revenue_rank
    FROM customer_totals AS t
    INNER JOIN customer_activity AS a
      ON t.customer_id = a.customer_id
    WHERE
      a.all_order_count >= 3
  )
  SELECT customer_id, revenue, order_count, average_amount, revenue_rank
  FROM scored
)
SELECT
  r.customer_id,
  r.revenue AS ranked_revenue,
  r.revenue_rank,
  r.average_amount,
  r.order_count
FROM ranked AS r
WHERE r.revenue_rank <= 3
ORDER BY r.revenue_rank, r.customer_id
LIMIT 2
