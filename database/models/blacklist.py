from sqlalchemy import Column, Integer, BigInteger

from database.model_base import Base


class Blacklist(Base):
    __tablename__ = 'blacklist'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, nullable=False)
