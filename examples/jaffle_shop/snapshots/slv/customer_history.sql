{% snapshot customer_history %}
{{ config({'check_cols': ['first_name', 'last_name'], 'invalidate_hard_deletes': True, 'strategy': 'check', 'target_schema': 'snapshots', 'unique_key': 'customer_id'}) }}

SELECT "customer_id", "first_name", "last_name" FROM {{ ref('slv_customers') }}
{% endsnapshot %}
