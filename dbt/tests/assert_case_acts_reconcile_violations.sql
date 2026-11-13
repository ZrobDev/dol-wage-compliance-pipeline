{{ config(severity='warn') }}

-- Measured on the first load: a case's violation total equals the sum of its act rows in
-- 100% of cases. A gap means an act column was misspelled or dropped from the unpivot.
with acts as (
    select case_id, sum(violations) as act_violations
    from {{ ref('stg_whd__case_acts') }}
    group by case_id
)

select cases.case_id, cases.case_violations, coalesce(acts.act_violations, 0) as act_violations
from {{ ref('stg_whd__cases') }} as cases
left join acts on cases.case_id = acts.case_id
where coalesce(cases.case_violations, 0) <> coalesce(acts.act_violations, 0)
