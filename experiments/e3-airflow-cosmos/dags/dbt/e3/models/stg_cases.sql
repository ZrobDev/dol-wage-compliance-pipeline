select i as case_id, i % 20 as sector_idx, (i * 37 % 50000) / 100.0 as back_wages
from range(1000000) t(i)
