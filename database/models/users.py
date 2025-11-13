from sqlalchemy import Column, Integer, BigInteger, Float
from sqlalchemy.orm import relationship

from database.model_base import Base


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, nullable=False)
    balance = Column(Float, nullable=False)
    items = relationship("UserItem", back_populates="user", lazy="subquery", foreign_keys="[UserItem.user_id]")
    trades = relationship("Trade", back_populates="user", lazy="subquery", foreign_keys="[Trade.user_id]")
    trade_items = relationship("Trade", back_populates="new_user", lazy="subquery", foreign_keys="[Trade.new_user_id]")
    cases = relationship("Case", back_populates="owner", lazy="subquery")
