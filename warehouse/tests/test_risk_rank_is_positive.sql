-- Singular test: risk ranks should be positive integers
select *
from {{ ref('mart_entity_scores') }}
where risk_rank < 1;
