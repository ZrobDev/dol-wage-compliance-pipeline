select
    state_code,
    state_name,
    census_region
from {{ ref('us_states') }}
