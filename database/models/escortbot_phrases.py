from sqlalchemy import Column, Integer, Text

from database.model_base import Base


class EscortBotPhrase(Base):
    __tablename__ = 'escortbot_phrases'
    id = Column(Integer, primary_key=True, autoincrement=True)
    escortbot_phrase = Column(Text, nullable=False)
