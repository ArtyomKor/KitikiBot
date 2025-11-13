from sqlalchemy import Column, Integer, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship

from database.model_base import Base


class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship('User', back_populates='trades', lazy='subquery', foreign_keys=[user_id], uselist=False)
    new_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    new_user = relationship('User', back_populates='trade_items', lazy='subquery', foreign_keys=[new_user_id], uselist=False)
    items = Column(JSON, nullable=False, default=[])
    completed = Column(Boolean, nullable=False, default=False)
