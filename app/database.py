from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

from app.config import settings

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    global engine, SessionLocal

    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        fallback_url = "sqlite:///./ai_agent.db"
        print(
            f"Database connection failed for '{settings.DATABASE_URL}'. "
            f"Falling back to local SQLite at '{fallback_url}'."
        )
        engine = create_engine(
            fallback_url,
            connect_args={"check_same_thread": False}
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
