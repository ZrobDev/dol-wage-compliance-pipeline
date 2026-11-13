with cases as (
    select
        case_id,
        state_code,
        findings_end_date,
        naics_key
    from {{ ref('stg_whd__cases') }}
)

select
    case_acts.case_act_id,
    case_acts.case_id,
    case_acts.act,
    case_acts.act_family,
    cases.naics_key,
    cases.state_code,
    cases.findings_end_date,
    case_acts.violations,
    case_acts.back_wages_agreed,
    case_acts.employees_due_back_wages,
    case_acts.cmp_assessed
from {{ ref('stg_whd__case_acts') }} as case_acts
inner join cases
    on case_acts.case_id = cases.case_id
