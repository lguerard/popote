from sqlalchemy import Column, String, Integer, DateTime
from app.database import Base

class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    icon = Column(String, nullable=False)
    progress = Column(Integer, default=0)
    goal = Column(Integer, default=1)
    unlocked_at = Column(DateTime(timezone=True), nullable=True)
    category = Column(String, default="collection")
