import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chronos.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_KEY = "chronos:scheduled"
