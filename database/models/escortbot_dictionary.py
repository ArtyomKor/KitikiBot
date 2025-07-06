from sqlalchemy import Column, Integer, String

from database.model_base import Base


class EscortBotDictionary(Base):
    __tablename__ = 'escortbot_dictionary'
    id = Column(Integer, primary_key=True, autoincrement=True)
    escortbot_char = Column(String(1), nullable=False)
    russian_char = Column(String(1), nullable=False)
