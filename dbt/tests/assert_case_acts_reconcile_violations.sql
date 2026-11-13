{{ config(severity='warn') }}

-- A case's violation total should equal the sum of its act rows. A gap can mean an act column
-- was misspelled or dropped from the unpivot. Measured on the full load (370,964 cases):
-- 2,690 cases (0.73%) differ, all with the case total above the act sum and none below, most
-- with findings ending 2020-2022. The source records violations no act column carries for
-- those cases. So this test stays a warning; a count well above 2,690 is the signal.
with acts as (
    select case_id, sum(violations) as act_violations
    from {{ ref('stg_whd__case_acts') }}
    group by case_id
)

select cases.case_id, cases.case_violations, coalesce(acts.act_violations, 0) as act_violations
from {{ ref('stg_whd__cases') }} as cases
left join acts on cases.case_id = acts.case_id
where coalesce(cases.case_violations, 0) <> coalesce(acts.act_violations, 0)
