import os

# Intentional planted secret for smoke-test / demo purposes only.
JWT_SECRET = "sk_live_REPLACE_WITH_REAL_KEY"
DATABASE_URL = os.environ.get("DATABASE_URL")
DEBUG = os.getenv("DEBUG", "false")
