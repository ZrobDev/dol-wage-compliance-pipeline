{% set first_day = modules.datetime.date(1980, 1, 1) %}
{% set last_day = modules.datetime.date(2030, 12, 31) %}

with date_spine as (
    select dateadd(
        day,
        row_number() over (order by seq4()) - 1,
        '{{ first_day }}'::date
    ) as date_day
    from table(generator(rowcount => {{ (last_day - first_day).days + 1 }}))
)

select
    date_day,
    year(date_day) as calendar_year,
    month(date_day) as calendar_month,
    quarter(date_day) as calendar_quarter,
    case when month(date_day) >= 10 then year(date_day) + 1 else year(date_day) end as federal_fiscal_year,
    case
        when month(date_day) between 10 and 12 then 1
        when month(date_day) between 1 and 3 then 2
        when month(date_day) between 4 and 6 then 3
        else 4
    end as federal_fiscal_quarter
from date_spine
