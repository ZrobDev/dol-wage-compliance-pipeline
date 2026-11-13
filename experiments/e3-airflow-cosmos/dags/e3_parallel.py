from datetime import datetime
from airflow.sdk import dag, task

@dag(schedule="*/5 * * * *", start_date=datetime(2026, 11, 1), catchup=False, max_active_runs=1)
def e3_parallel():
    @task
    def work(i: int) -> int:
        rows = [{"id": n, "v": n * i} for n in range(300_000)]  # ~100 MB transient
        return sum(r["v"] for r in rows) % 997
    work.expand(i=[1, 2, 3, 4])

e3_parallel()
