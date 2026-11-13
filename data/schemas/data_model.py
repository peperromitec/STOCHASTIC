from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from .base import Base

class Data(Base):
    __tablename__ = 'data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    gender = Column(String(1)) 
    age = Column(Integer)
    bicycle_id = Column(Text)
    begin_station = Column(Text)
    end_station = Column(Text)
    begin_time = Column(DateTime)
    end_time = Column(DateTime)
    # NULL para viajes anteriores a la incorporación de trazabilidad.
    file_register_id = Column(Integer, ForeignKey('file_register.id'), index=True)
