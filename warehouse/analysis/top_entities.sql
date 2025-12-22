-- dbt analysis: top entities by chokepoint score
select * from {{ ref('mart_entity_scores') }} order by chokepoint_score desc limit 25;
