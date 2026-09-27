"""MySQL connection for DATA-260 HW4 (s1346_rel) using SQLAlchemy."""
import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

PREFIX = "s1346"
DB_NAME = f"{PREFIX}_rel"

MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

# Required name (HW4 Part 2): the session factory every request uses.
db_session_basede26 = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


def get_db():
    """FastAPI dependency: one DB session per request, always closed."""
    db = db_session_basede26()
    try:
        yield db
    finally:
        db.close()
