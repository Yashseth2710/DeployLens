from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# One connection was the original setting, on the reasoning that a serverless invocation
# handles one request and Neon's pooled endpoint does the real pooling. That is true of
# the deployed shape and badly wrong everywhere else: a page opens five requests at once,
# and with a single connection they queue single file. Worse, the activity endpoint holds
# its connection while it waits on GitHub, so every other request on the page waits for a
# network call it has nothing to do with.
#
# Neon's pooled endpoint is pgbouncer and is happy with far more than this. The cost of a
# few idle connections is nothing next to a page that takes fifteen seconds to answer.
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    # Neon suspends idle compute and drops what it was holding. pre_ping catches a dead
    # connection at checkout; recycling stops us keeping one long enough to go stale.
    pool_recycle=300,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
