from sqlalchemy import Column, Integer, String, Boolean, Date
from datetime import date
from database import Base

class DailyEntry(Base):
    __tablename__ = "daily_entries"

    id = Column(Integer, primary_key=True, index=True)
    age = Column(Integer)
    screen_minutes = Column(Integer)
    evening_usage = Column(Boolean)
    guidance = Column(String)
    entry_date = Column(Date, default=date.today)
