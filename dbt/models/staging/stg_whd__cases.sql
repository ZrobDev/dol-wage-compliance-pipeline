with deduplicated as (
    select
        try_to_number(payload:case_id::string) as case_id,
        trim(payload:trade_nm::string) as trade_name,
        trim(payload:legal_name::string) as legal_name,
        trim(payload:cty_nm::string) as city,
        upper(trim(payload:st_cd::string)) as state_code,
        trim(payload:zip_cd::string) as zip_code,
        trim(payload:naic_cd::string) as naics_code,
        -- Digits only; null, empty or one-digit codes become UNKNOWN.
        case
            when length(coalesce(regexp_replace(payload:naic_cd::string, '[^0-9]', ''), '')) < 2
                then 'UNKNOWN'
            else regexp_replace(payload:naic_cd::string, '[^0-9]', '')
        end as naics_key,
        trim(payload:naics_code_description::string) as naics_description,
        try_to_date(payload:findings_start_date::string) as findings_start_date,
        try_to_date(payload:findings_end_date::string) as findings_end_date,
        case
            -- The exact source domain is checked after the first load.
            when upper(trim(payload:flsa_repeat_violator::string)) in ('R', 'RV', 'Y', 'YES', 'TRUE', '1') then true
            else false
        end as is_flsa_repeat_violator,
        try_to_number(payload:case_violtn_cnt::string) as case_violations,
        try_to_number(payload:ee_violtd_cnt::string) as employees_violated,
        try_to_decimal(payload:bw_atp_amt::string, 18, 2) as back_wages_agreed,
        try_to_number(payload:ee_atp_cnt::string) as employees_due_back_wages,
        try_to_decimal(payload:cmp_assd::string, 18, 2) as cmp_assessed,
        try_to_timestamp_ntz(payload:load_dt::string) as load_dt,
        loaded_at,
        source_file,
        file_row
    from {{ source('whd', 'whd_enforcement') }}
    qualify row_number() over (
        partition by case_id
        order by load_dt desc, loaded_at desc, source_file desc, file_row desc
    ) = 1
)

select
    case_id,
    trade_name,
    legal_name,
    city,
    state_code,
    zip_code,
    naics_code,
    naics_key,
    naics_description,
    findings_start_date,
    findings_end_date,
    is_flsa_repeat_violator,
    case_violations,
    employees_violated,
    back_wages_agreed,
    employees_due_back_wages,
    cmp_assessed,
    load_dt,
    loaded_at,
    source_file
from deduplicated
