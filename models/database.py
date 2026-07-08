import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import Config

DATABASE_URL = Config.DATABASE_URL

# Fallback to local SQLite if DATABASE_URL is not set
if not DATABASE_URL:
    import os
    os.makedirs("./db", exist_ok=True)
    DATABASE_URL = "sqlite:///./db/metadata.db"
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI DB session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
