from sqlalchemy import Column, Integer, Text, Float
from sqlalchemy.orm import relationship

from database.model_base import Base


class Case(Base):
    __tablename__ = 'cases'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    image = Column(Text, nullable=True)
    items = relationship("CaseItem", back_populates="case", lazy="subquery")
