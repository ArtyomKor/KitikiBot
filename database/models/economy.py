from sqlalchemy import Column, Float, Integer

from database.model_base import Base


class Economy(Base):
    __tablename__ = 'economy'
    symbol_coast = Column(Float, nullable=False, primary_key=True)
    min_message_length = Column(Integer, nullable=False)
    max_message_length = Column(Integer, nullable=False)
    gif_coast = Column(Float, nullable=False)
    sticker_coast = Column(Float, nullable=False)
    photo_coast = Column(Float, nullable=False)
    video_coast = Column(Float, nullable=False)
    voice_message_coast = Column(Float, nullable=False)
    video_message_coast = Column(Float, nullable=False)
    start_balance = Column(Float, nullable=False)
    casino_coast = Column(Float, nullable=False)
    casino_chance = Column(Integer, nullable=False)
    komaru_limit = Column(Integer, nullable=False)


def create_empty_economy_settings():
    economy_settings = Economy(symbol_coast=0,
                               min_message_length=0,
                               max_message_length=0,
                               gif_coast=0,
                               sticker_coast=0,
                               photo_coast=0,
                               video_coast=0,
                               voice_message_coast=0,
                               video_message_coast=0,
                               start_balance=0,
                               casino_coast=0,
                               casino_chance=0,
                               komaru_limit=0)
    return economy_settings
