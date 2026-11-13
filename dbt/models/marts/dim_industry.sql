with cases as (
    select
        case_id,
        naics_code,
        naics_description,
        naics_key
    from {{ ref('stg_whd__cases') }}
),
descriptions as (
    select
        naics_key,
        naics_description,
        row_number() over (
            partition by naics_key
            order by count(*) desc, naics_description asc nulls last
        ) as description_rank
    from cases
    group by naics_key, naics_description
),
industry_counts as (
    select naics_key, count(*) as case_count
    from cases
    group by naics_key
)

select
    industry_counts.naics_key,
    coalesce(naics_sectors.sector_code, 'UNMAPPED') as sector_code,
    coalesce(naics_sectors.sector_name, 'Unmapped NAICS code') as sector_name,
    naics_sectors.sector_code is not null as is_mapped,
    descriptions.naics_description,
    industry_counts.case_count
from industry_counts
left join {{ ref('naics_sectors') }} as naics_sectors
    on left(industry_counts.naics_key, 2) = naics_sectors.naics_2digit
left join descriptions
    on industry_counts.naics_key = descriptions.naics_key
    and descriptions.description_rank = 1
