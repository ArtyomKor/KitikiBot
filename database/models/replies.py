from sqlalchemy import Column, Integer, BigInteger, Text

from database.model_base import Base


class Reply(Base):
    __tablename__ = 'replies'
    id = Column(Integer, primary_key=True, autoincrement=True)
    media_id = Column(BigInteger, nullable=False)
    rare = Column(Text, nullable=True)
    epic = Column(Text, nullable=True)
    gif_id = Column(Text, nullable=True)
