import os

# Intentional planted secret for smoke-test / demo purposes only.
JWT_SECRET = "sk_live_FAKE-DEMO-KEY-DO-NOT-USE-0000"
DATABASE_URL = os.environ.get("DATABASE_URL")
DEBUG = os.getenv("DEBUG", "false")
