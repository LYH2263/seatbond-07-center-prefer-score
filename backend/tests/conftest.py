import os

# The app builds its default engine at import time; integration tests override
# get_db with their own in-memory SQLite, so point the ambient URL at SQLite too
# and disable startup seeding before any app module is imported.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_EMPTY", "false")
