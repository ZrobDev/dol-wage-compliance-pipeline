FROM apache/airflow:3.3.2
USER root
RUN mkdir /opt/dbt-venv && chown airflow: /opt/dbt-venv
USER airflow
RUN pip install --no-cache-dir "apache-airflow==3.3.2" "astronomer-cosmos==1.15.1"
# dbt in its own venv so its pins can't break Airflow's
RUN python -m venv /opt/dbt-venv && /opt/dbt-venv/bin/pip install --no-cache-dir dbt-core==1.11.16 dbt-duckdb==1.11.0
