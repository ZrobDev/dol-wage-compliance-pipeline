with cases as (
    select
        case_id,
        state_code,
        findings_end_date,
        case_violations,
        employees_due_back_wages,
        back_wages_agreed,
        cmp_assessed,
        naics_key
    from {{ ref('stg_whd__cases') }}
    where findings_end_date is not null
)

select
    dim_industry.sector_code,
    dim_industry.sector_name,
    cases.state_code,
    dim_date.federal_fiscal_year as fiscal_year,
    count(distinct cases.case_id) as cases,
    sum(cases.case_violations) as case_violations,
    sum(cases.employees_due_back_wages) as employees_due_back_wages,
    sum(cases.back_wages_agreed) as back_wages_agreed,
    sum(cases.cmp_assessed) as cmp_assessed
from cases
inner join {{ ref('dim_industry') }} as dim_industry
    on cases.naics_key = dim_industry.naics_key
inner join {{ ref('dim_date') }} as dim_date
    on cases.findings_end_date = dim_date.date_day
group by
    dim_industry.sector_code,
    dim_industry.sector_name,
    cases.state_code,
    dim_date.federal_fiscal_year
