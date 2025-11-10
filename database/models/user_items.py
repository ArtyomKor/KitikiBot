from sqlalchemy import Column, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from database.model_base import Base


class UserItem(Base):
    __tablename__ = "user_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship("User", foreign_keys=[user_id], lazy="subquery", uselist=False)
    case_item_id = Column(Integer, ForeignKey('case_items.id'), nullable=False)
    case_item = relationship("CaseItem", foreign_keys=[case_item_id], lazy="subquery", uselist=False)
    new_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    new_user = relationship("User", foreign_keys=[new_user_id], lazy="subquery", uselist=False)
    trade_confirmed = Column(Boolean, nullable=True)
    sold = Column(Boolean, nullable=False, default=False)
