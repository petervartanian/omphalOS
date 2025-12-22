-- Audit metric: match rate (how many shipments auto-matched vs reviewed)
-- Parameters: none
select
  sum(case when status = 'MATCHED' then 1 else 0 end) as matched,
  sum(case when status = 'REVIEW' then 1 else 0 end) as review,
  count(*) as total,
  round( (sum(case when status = 'MATCHED' then 1 else 0 end) * 1.0) / nullif(count(*),0), 6) as match_rate,
  round( (sum(case when status = 'REVIEW' then 1 else 0 end) * 1.0) / nullif(count(*),0), 6) as review_fraction
from entity_matches;
