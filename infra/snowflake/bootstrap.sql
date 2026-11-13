-- Snowflake bootstrap for dol-wage-compliance-pipeline (M1).
-- Run once, as ACCOUNTADMIN, in a Snowsight worksheet on account DOL_WAGE ("Run All").
-- Idempotent: every object is CREATE ... IF NOT EXISTS. The monitor is never replaced, because
-- replacing it would reset the month's used credits; change its quota with ALTER RESOURCE MONITOR.
-- No secrets live here. The service user's public key is set afterwards; see the end of the file.

USE ROLE ACCOUNTADMIN;

-- Check: this must print DOL_WAGE. Stop here if it does not.
-- (A Snowflake Scripting guard cannot run yet: scripting needs an active warehouse,
-- and the warehouse is created below. Run from a client, check the account first.)
SELECT CURRENT_ACCOUNT_NAME() AS must_be_dol_wage;

-- Cost cap. Standard on AWS us-east-1 is $2.00/credit, so 2 credits is $4/month
-- (about 2 hours of an XS warehouse). It covers warehouse compute only, not cloud services.
-- NOTIFY reaches account admins who enabled notifications in Snowsight.
CREATE RESOURCE MONITOR IF NOT EXISTS WHD_MONTHLY WITH
  CREDIT_QUOTA = 2
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 100 PERCENT DO SUSPEND;

CREATE WAREHOUSE IF NOT EXISTS WHD_WH WITH
  WAREHOUSE_SIZE = XSMALL
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  STATEMENT_TIMEOUT_IN_SECONDS = 600
  COMMENT = 'dol-wage-compliance-pipeline: ingest COPY and dbt';
-- Set separately so the assignment also holds for a warehouse created before the monitor.
ALTER WAREHOUSE WHD_WH SET RESOURCE_MONITOR = WHD_MONTHLY;

-- Account-wide ceiling: every warehouse, including the trial's default one used by Snowsight.
-- 3 credits (~$6/month) counts every warehouse together: worksheet use also draws it down and
-- can suspend WHD_WH before the pipeline reaches its own 2 credits. That is the intended ceiling.
CREATE RESOURCE MONITOR IF NOT EXISTS WHD_ACCOUNT WITH
  CREDIT_QUOTA = 3
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 100 PERCENT DO SUSPEND;
ALTER ACCOUNT SET RESOURCE_MONITOR = WHD_ACCOUNT;

-- One role for loading and transforming. Granted to SYSADMIN so admins inherit it.
CREATE ROLE IF NOT EXISTS WHD_PIPELINE;
GRANT ROLE WHD_PIPELINE TO ROLE SYSADMIN;
GRANT USAGE, OPERATE ON WAREHOUSE WHD_WH TO ROLE WHD_PIPELINE;

CREATE DATABASE IF NOT EXISTS WHD;
GRANT USAGE ON DATABASE WHD TO ROLE WHD_PIPELINE;
CREATE SCHEMA IF NOT EXISTS WHD.RAW;
CREATE SCHEMA IF NOT EXISTS WHD.STAGING;
CREATE SCHEMA IF NOT EXISTS WHD.MARTS;
GRANT OWNERSHIP ON SCHEMA WHD.RAW TO ROLE WHD_PIPELINE COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA WHD.STAGING TO ROLE WHD_PIPELINE COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA WHD.MARTS TO ROLE WHD_PIPELINE COPY CURRENT GRANTS;

-- Raw landing objects, owned by the pipeline role.
USE ROLE WHD_PIPELINE;
CREATE STAGE IF NOT EXISTS WHD.RAW.WHD_STAGE
  COMMENT = 'Gzipped JSON pages from the DOL WHD enforcement API';
CREATE TABLE IF NOT EXISTS WHD.RAW.WHD_ENFORCEMENT (
  payload     VARIANT       COMMENT 'One API record, as returned',
  source_file STRING        COMMENT 'Stage file the record came from (one API page)',
  file_row    NUMBER        COMMENT 'Row number within that file',
  loaded_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
USE ROLE ACCOUNTADMIN;

-- Service user: key-pair auth only (TYPE = SERVICE has no password and no MFA).
CREATE USER IF NOT EXISTS WHD_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = WHD_PIPELINE
  DEFAULT_WAREHOUSE = WHD_WH
  DEFAULT_NAMESPACE = WHD.RAW
  COMMENT = 'dol-wage-compliance-pipeline ingest and dbt';
GRANT ROLE WHD_PIPELINE TO USER WHD_SVC;

-- Let the pipeline role measure its own cost (WAREHOUSE_METERING_HISTORY and the other
-- ACCOUNT_USAGE views) and run the cost-guard test on its own monitor. The account-wide
-- monitor WHD_ACCOUNT stays ACCOUNTADMIN-only.
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE WHD_PIPELINE;
GRANT MONITOR, MODIFY ON RESOURCE MONITOR WHD_MONTHLY TO ROLE WHD_PIPELINE;

-- After this script: generate the key pair locally (private key straight into the secrets
-- manager, never on disk or screen), then set the public key body here:
--   ALTER USER WHD_SVC SET RSA_PUBLIC_KEY = '<public key body, no BEGIN/END lines>';
--   DESC USER WHD_SVC;  -- RSA_PUBLIC_KEY_FP is set
--
-- Key rotation without downtime: set the new public key in the second slot, switch the secret
-- to the new private key, confirm a connection, then clear the old slot.
--   ALTER USER WHD_SVC SET RSA_PUBLIC_KEY_2 = '<new public key body>';
--   ALTER USER WHD_SVC UNSET RSA_PUBLIC_KEY;
-- No network policy yet: the operator's IP is dynamic. One arrives with CI in M3.
