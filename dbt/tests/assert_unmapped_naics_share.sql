{{ config(severity='warn') }}

select
    sum(case when not is_mapped then case_count else 0 end) / nullif(sum(case_count), 0) as unmapped_share
from {{ ref('dim_industry') }}
having unmapped_share > 0.05
