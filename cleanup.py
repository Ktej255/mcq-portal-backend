import sqlite3

c = sqlite3.connect('production.db')

tables_to_drop = [
    'job_execution_registry',
    'operational_metrics',
    'system_events',
    'execution_traces',
    '_alembic_tmp_attempts',
    '_alembic_tmp_users'
]

indexes_to_drop = [
    'ix_attempt_answers_attempt_id',
    'ix_attempt_answers_question_id',
    'ix_execution_traces_trace_id',
    'ix_execution_traces_created_at',
    'ix_execution_traces_function_name',
    'ix_execution_traces_id',
    'ix_execution_traces_module_name',
    'ix_execution_traces_parent_trace_id',
    'ix_execution_traces_status'
]

for t in tables_to_drop:
    try:
        c.execute(f"DROP TABLE IF EXISTS {t}")
    except Exception as e:
        print(e)

for i in indexes_to_drop:
    try:
        c.execute(f"DROP INDEX IF EXISTS {i}")
    except Exception as e:
        print(e)

c.commit()
print("Cleaned up failed migration artifacts.")
