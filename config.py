import os

# HMAC signing key - in production, load from environment variable
SIGNING_KEY = os.getenv("WEBHOOK_SIGNING_KEY", "my-super-secret-key-2024")

# Retry intervals in seconds: 30s, 5min, 30min
RETRY_INTERVALS = [30, 300, 1800]

# HTTP request timeout in seconds
REQUEST_TIMEOUT = 10

# Database file path
DATABASE_PATH = os.getenv("DATABASE_PATH", "webhook_engine.db")