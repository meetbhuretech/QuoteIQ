from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(dag_id="quoteiq_model_registration", start_date=datetime(2024, 1, 1), schedule=None, catchup=False, tags=["quoteiq"]) as dag:
    BashOperator(task_id="register_candidate", bash_command="python -m quoteiq_ml.register")
