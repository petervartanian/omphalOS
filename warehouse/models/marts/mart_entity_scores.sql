-- Mart: entity scoring, enriched for review workflows
with base as (
  select * from {{ ref('stg_entity_scores') }}
),
ranked as (
  select
    *,
    row_number() over (order by chokepoint_score desc, total_value_usd desc, entity_id asc) as risk_rank
  from base
)
select * from ranked
