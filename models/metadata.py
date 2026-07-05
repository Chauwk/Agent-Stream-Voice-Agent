from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from models.database import Base

class Company(Base):
    __tablename__ = "companies"
    
    company_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    metadata_json = Column(JSON, default={}, nullable=True)  # custom settings/attributes
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

class DocumentLog(Base):
    __tablename__ = "document_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id = Column(String, index=True, nullable=False)
    filename = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending, processed, failed
