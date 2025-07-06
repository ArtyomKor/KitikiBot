from sqlalchemy import Column, Integer, Text

from database.model_base import Base


class EscortBotAdminCall(Base):
    __tablename__ = 'escortbot_admin_calls'
    id = Column(Integer, primary_key=True, autoincrement=True)
    escortbot_admin_call = Column(Text, nullable=False)
