from sqlalchemy import Column, Integer, BigInteger, Text

from database.model_base import Base


class Emotion(Base):
    __tablename__ = 'emotions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    media_id = Column(BigInteger, nullable=False)
    emoticon = Column(Text, nullable=False)
