import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chronos.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_KEY = "chronos:scheduled"
DEAD_LETTER_QUEUE_KEY = "chronos:dead-letter"
WORKER_LEASE_SECONDS = int(os.getenv("WORKER_LEASE_SECONDS", "60"))
