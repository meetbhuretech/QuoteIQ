from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(dag_id="quoteiq_model_deployment_approval", start_date=datetime(2024, 1, 1), schedule=None, catchup=False, tags=["quoteiq"]) as dag:
    BashOperator(
        task_id="wait_for_human_approval",
        bash_command="python -c \"print('Manual approval required. This DAG does not promote models.')\"",
    )
