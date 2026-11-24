from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="quoteiq_scheduled_retraining",
    start_date=datetime(2024, 1, 1),
    schedule="0 2 * * 0",
    catchup=False,
    tags=["quoteiq"],
) as dag:
    validate = BashOperator(task_id="validate_dataset", bash_command="python -m quoteiq_ml.validate")
    train = BashOperator(task_id="train_models", bash_command="python -m quoteiq_ml.train")
    evaluate = BashOperator(task_id="evaluate", bash_command="python -m quoteiq_ml.evaluate")
    register = BashOperator(task_id="register_candidate", bash_command="python -m quoteiq_ml.register")
    validate >> train >> evaluate >> register
