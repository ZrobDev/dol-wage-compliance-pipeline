# Airflow 3 + Cosmos for the WHD pipeline (M2). Build from the repo root:
#   docker build -f infra/airflow/Dockerfile -t whd-airflow:local .
# The repo-root .dockerignore is an allowlist, so state/ and .env never enter a layer.
FROM apache/airflow:slim-3.3.2-python3.13@sha256:881c35bfb1f6b76d233dd402b7228b5c37003702068b865db5db76061458b2bd

USER root
# Code only. The state dir (/var/lib/pipeline/state) is deliberately NOT created here: it must
# come from the bind mount, or the pipeline's existence check could not catch a forgotten volume
# (ADR 0004).
RUN install -d -o airflow -g 0 /opt/pipeline \
    # The api-server writes its generated password file here. A new named volume copies this
    # path's ownership; without it the volume is root-owned and UID 50000 cannot write.
    && install -d -o airflow -g 0 -m 0700 /opt/airflow/auth
USER airflow

# Airflow, the postgres extra and Cosmos, every version pinned (transitive ones too). Regenerate
# with the command in infra/airflow/README.md, never by hand.
COPY --chown=airflow:0 infra/airflow/requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt "uv==0.13.6"

# The pipeline and dbt in their own venv, from uv.lock, so their pins cannot break Airflow's.
WORKDIR /opt/pipeline
COPY --chown=airflow:0 pyproject.toml uv.lock README.md LICENSE .python-version ./
COPY --chown=airflow:0 src/ src/
COPY --chown=airflow:0 dbt/ dbt/
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/pipeline/.venv
RUN uv sync --frozen --no-dev --python /usr/python/bin/python3.13

# Cosmos reads a prebuilt manifest (LoadMode.DBT_MANIFEST; dbt ls timed out the DAG parse in E3).
# dbt parse opens no connection; the placeholders only satisfy env_var() in profiles.yml.
RUN SNOWFLAKE_ACCOUNT=build-placeholder SNOWFLAKE_USER=build-placeholder \
    .venv/bin/dbt parse --project-dir dbt --profiles-dir dbt --target homelab \
    && test -s dbt/target/manifest.json

COPY --chown=airflow:0 airflow/dags/ /opt/airflow/dags/
WORKDIR /opt/airflow

# The commit this image was built from, read by the drift task and checked by deploy.sh. Last, so
# a new revision rebuilds no other layer. deploy.sh passes it; a bare `docker compose build` fails.
ARG REVISION
RUN test -n "$REVISION" || { echo "build with --build-arg REVISION=<git sha> (deploy.sh does)" >&2; exit 1; }
LABEL org.opencontainers.image.revision=$REVISION
ENV PIPELINE_REVISION=$REVISION
