from sqlalchemy import Column, Integer, String, DateTime

from schemas.base import Base


class FileRegister(Base):
    __tablename__ = 'file_register'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255), unique=True) # unique evita registrar el mismo archivo dos veces
    process_date = Column(DateTime)