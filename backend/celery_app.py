from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Connect celery to Redis broker
celery_app = Celery(
    "tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks']
)
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata', 
    enable_utc=True,  
    task_always_eager=False, 
    task_eager_propagates=False,
    worker_prefetch_multiplier = 1,
    task_acks_late = True,
    broker_pool_limit=None
)
