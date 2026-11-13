{{ config(materialized='table') }}

-- One row per case: the newest raw version. Raw is append-only and holds duplicates
-- (the loader uses COPY FORCE), so every staging model reads the survivor from here.
select
    payload,
    try_to_number(payload:case_id::string) as case_id,
    try_to_timestamp_ntz(payload:load_dt::string) as load_dt,
    loaded_at,
    source_file
from {{ source('whd', 'whd_enforcement') }}
qualify row_number() over (
    partition by case_id
    order by load_dt desc nulls last, loaded_at desc, source_file desc, file_row desc
) = 1
