select s.naics_sector, s.sector_name, count(*) as cases, sum(c.back_wages) as back_wages
from {{ ref('stg_cases') }} c join {{ ref('sectors') }} s on s.sector_idx = c.sector_idx
group by 1, 2
