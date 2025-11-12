from sqlalchemy import Column, Integer, ForeignKey, BigInteger, String, Float, Text, Boolean
from sqlalchemy.orm import relationship

from database.model_base import Base


class CaseItem(Base):
    __tablename__ = 'case_items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey('cases.id'), nullable=False)
    case = relationship("Case", foreign_keys=[case_id], lazy="subquery", uselist=False)
    name = Column(Text, nullable=False)
    gif_message_id = Column(BigInteger, nullable=False)
    gif_message_chat_id = Column(BigInteger, nullable=False)
    emoticon = Column(String(8), nullable=False)
    price = Column(Float, nullable=False)
    collection = Column(Boolean, nullable=False, default=False)
