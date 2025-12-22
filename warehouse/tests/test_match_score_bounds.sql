-- Singular test: match scores should fall in [0, 1]
select *
from {{ ref('mart_shipments_by_entity') }}
where match_score is not null and (match_score < 0 or match_score > 1);
