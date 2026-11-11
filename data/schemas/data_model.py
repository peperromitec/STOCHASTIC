from sqlalchemy import Column, Integer, String, DateTime
from schemas.base import Base

class Data(Base):
    __tablename__ = 'data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    gender = Column(String(1)) 
    age = Column(Integer)
    bicycle_id = Column(Integer)
    begin_station = Column(String(7)) # Usar String en lugar de Varchar
    end_station = Column(String(7))
    begin_time = Column(DateTime)
    end_time = Column(DateTime)