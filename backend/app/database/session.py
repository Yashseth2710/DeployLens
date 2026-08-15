from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# NullPool territory: each serverless invocation is a fresh process, so a local pool
# would never be reused. Neon's pooled endpoint does the pooling instead, and
# pool_pre_ping absorbs connections dropped while the compute was suspended.
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=0,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
