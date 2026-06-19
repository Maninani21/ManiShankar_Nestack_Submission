# config file 

SECRET_KEY = "mywebhooksecret123"

# retry timing (in seconds)
r1 = 30        # 30 sec
r2 = 60 * 5    # 5 min
r3 = 60 * 30   # 30 min

RETRY_INTERVALS = [r1, r2, r3]

TIMEOUT = 10

DB = "webhooks.db"