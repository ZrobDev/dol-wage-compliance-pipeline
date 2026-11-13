{% set acts = [
    {'act': 'flsa', 'violations': 'flsa_violtn_cnt', 'back_wages': 'flsa_bw_atp_amt', 'employees': 'flsa_ee_atp_cnt', 'cmp': 'flsa_cmp_assd_amt'},
    {'act': 'flsa_cl', 'violations': 'flsa_cl_violtn_cnt', 'back_wages': none, 'employees': none, 'cmp': 'flsa_cl_cmp_assd_amt'},
    {'act': 'flsa_smw14', 'violations': 'flsa_smw14_violtn_cnt', 'back_wages': 'flsa_smw14_bw_amt', 'employees': 'flsa_smw14_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_smwpw', 'violations': 'flsa_smwpw_violtn_cnt', 'back_wages': 'flsa_smwpw_bw_atp_amt', 'employees': 'flsa_smwpw_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_smwap', 'violations': 'flsa_smwap_violtn_cnt', 'back_wages': 'flsa_smwap_bw_atp_amt', 'employees': 'flsa_smwap_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_smwft', 'violations': 'flsa_smwft_violtn_cnt', 'back_wages': 'flsa_smwft_bw_atp_amt', 'employees': 'flsa_smwft_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_smwl', 'violations': 'flsa_smwl_violtn_cnt', 'back_wages': 'flsa_smwl_bw_atp_amt', 'employees': 'flsa_smwl_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_smwmg', 'violations': 'flsa_smwmg_violtn_cnt', 'back_wages': 'flsa_smwmg_bw_atp_amt', 'employees': 'flsa_smwmg_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_smwsl', 'violations': 'flsa_smwsl_violtn_cnt', 'back_wages': 'flsa_smwsl_bw_atp_amt', 'employees': 'flsa_smwsl_ee_atp_cnt', 'cmp': none},
    {'act': 'flsa_hmwkr', 'violations': 'flsa_hmwkr_violtn_cnt', 'back_wages': 'flsa_hmwkr_bw_atp_amt', 'employees': 'flsa_hmwkr_ee_atp_cnt', 'cmp': 'flsa_hmwkr_cmp_assd_amt'},
    {'act': 'sca', 'violations': 'sca_violtn_cnt', 'back_wages': 'sca_bw_atp_amt', 'employees': 'sca_ee_atp_cnt', 'cmp': none},
    {'act': 'dbra', 'violations': 'dbra_violtn_cnt', 'back_wages': 'dbra_bw_atp_amt', 'employees': 'dbra_ee_atp_cnt', 'cmp': none},
    {'act': 'ccpa', 'violations': 'ccpa_violtn_cnt', 'back_wages': 'ccpa_bw_atp_amt', 'employees': 'ccpa_ee_atp_cnt', 'cmp': none},
    {'act': 'ca', 'violations': 'ca_violtn_cnt', 'back_wages': 'ca_bw_atp_amt', 'employees': 'ca_ee_atp_cnt', 'cmp': none},
    {'act': 'pca', 'violations': 'pca_violtn_cnt', 'back_wages': 'pca_bw_atp_amt', 'employees': 'pca_ee_atp_cnt', 'cmp': none},
    {'act': 'h2b', 'violations': 'h2b_violtn_cnt', 'back_wages': 'h2b_bw_atp_amt', 'employees': 'h2b_ee_atp_cnt', 'cmp': none},
    {'act': 'sraw', 'violations': 'sraw_violtn_cnt', 'back_wages': 'sraw_bw_atp_amt', 'employees': 'sraw_ee_atp_cnt', 'cmp': none},
    {'act': 'mspa', 'violations': 'mspa_violtn_cnt', 'back_wages': 'mspa_bw_atp_amt', 'employees': 'mspa_ee_atp_cnt', 'cmp': 'mspa_cmp_assd_amt'},
    {'act': 'h1b', 'violations': 'h1b_violtn_cnt', 'back_wages': 'h1b_bw_atp_amt', 'employees': 'h1b_ee_atp_cnt', 'cmp': 'h1b_cmp_assd_amt'},
    {'act': 'fmla', 'violations': 'fmla_violtn_cnt', 'back_wages': 'fmla_bw_atp_amt', 'employees': 'fmla_ee_atp_cnt', 'cmp': 'fmla_cmp_assd_amt'},
    {'act': 'h2a', 'violations': 'h2a_violtn_cnt', 'back_wages': 'h2a_bw_atp_amt', 'employees': 'h2a_ee_atp_cnt', 'cmp': 'h2a_cmp_assd_amt'},
    {'act': 'osha', 'violations': 'osha_violtn_cnt', 'back_wages': 'osha_bw_atp_amt', 'employees': 'osha_ee_atp_cnt', 'cmp': 'osha_cmp_assd_amt'},
    {'act': 'h1a', 'violations': 'h1a_violtn_cnt', 'back_wages': 'h1a_bw_atp_amt', 'employees': 'h1a_ee_atp_cnt', 'cmp': 'h1a_cmp_assd_amt'},
    {'act': 'crew', 'violations': 'crew_violtn_cnt', 'back_wages': 'crew_bw_atp_amt', 'employees': 'crew_ee_atp_cnt', 'cmp': 'crew_cmp_assd_amt'},
    {'act': 'cwhssa', 'violations': 'cwhssa_violtn_cnt', 'back_wages': 'cwhssa_bw_amt', 'employees': 'cwhssa_ee_cnt', 'cmp': none},
    {'act': 'eppa', 'violations': 'eppa_violtn_cnt', 'back_wages': 'eppa_bw_atp_amt', 'employees': 'eppa_ee_cnt', 'cmp': 'eppa_cmp_assd_amt'},
    {'act': 'eev', 'violations': 'eev_violtn_cnt', 'back_wages': none, 'employees': none, 'cmp': none}
] %}

with deduplicated as (
    select case_id, payload from {{ ref('base_whd__enforcement') }}
),
unpivoted as (
    {% for item in acts %}
    select
        case_id || '-{{ item['act'] }}' as case_act_id,
        case_id,
        '{{ item['act'] }}' as act,
        {% if item['act'].startswith('flsa') %}'FLSA'{% else %}'{{ item['act'].upper() }}'{% endif %} as act_family,
        try_to_number(payload:{{ item['violations'] }}::string) as violations,
        {% if item['back_wages'] %}try_to_decimal(payload:{{ item['back_wages'] }}::string, 18, 2){% else %}null::decimal(18, 2){% endif %} as back_wages_agreed,
        {% if item['employees'] %}try_to_number(payload:{{ item['employees'] }}::string){% else %}null::number{% endif %} as employees_due_back_wages,
        {% if item['cmp'] %}try_to_decimal(payload:{{ item['cmp'] }}::string, 18, 2){% else %}null::decimal(18, 2){% endif %} as cmp_assessed
    from deduplicated
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

-- Excludes FLSA back-wage breakdowns and flsa_cl_minor_cnt because they are not acts.
select *
from unpivoted
where violations > 0
   or back_wages_agreed > 0
   or employees_due_back_wages > 0
   or cmp_assessed > 0
