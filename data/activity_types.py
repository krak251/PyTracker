from sqlalchemy import Column, Integer, String, orm
from .db_session import SqlAlchemyBase


class ActivityType(SqlAlchemyBase):
    __tablename__ = 'activity_types'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    activities = orm.relationship("Activity", back_populates="activity_type_rel")

    def __repr__(self):
        return f"<ActivityType> {self.name}"
