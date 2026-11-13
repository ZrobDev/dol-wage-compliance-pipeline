-- One row per sector x state x fiscal year, and every dated case lands in exactly one cell:
-- the cell counts must add up to the staging cases that have a findings end date.
with duplicate_cells as (
    select 'duplicate cell' as problem, count(*) as n
    from {{ ref('agg_industry_state_year') }}
    group by sector_code, state_code, fiscal_year
    having count(*) > 1
),

totals as (
    select
        'case total mismatch' as problem,
        (select coalesce(sum(cases), 0) from {{ ref('agg_industry_state_year') }})
        - (select count(*) from {{ ref('stg_whd__cases') }} where findings_end_date is not null)
            as n
)

select * from duplicate_cells
union all
select * from totals where n <> 0
