from sqlalchemy import Column, Integer, String, DateTime, BigInteger

from .base import Base


class FileRegister(Base):
    __tablename__ = 'file_register'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255), unique=True) # unique evita registrar el mismo archivo dos veces
    process_date = Column(DateTime)
    row_count = Column(BigInteger)
    content_sha256 = Column(String(64), index=True)
