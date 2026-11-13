-- The public aggregate's privacy rule, checked on the values themselves: a cell is suppressed
-- exactly when it has fewer than 3 cases, and a suppressed cell carries no measure at all.
select *
from {{ ref('agg_industry_state_year') }}
where is_suppressed is distinct from (cases < 3)
   or (
       is_suppressed
       and (
           case_violations is not null
           or employees_due_back_wages is not null
           or back_wages_agreed is not null
           or cmp_assessed is not null
       )
   )
