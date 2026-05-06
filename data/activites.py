import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, BigInteger, orm
from .db_session import SqlAlchemyBase


class Activity(SqlAlchemyBase):
    __tablename__ = 'activities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))

    activity_type_id = Column(Integer, ForeignKey('activity_types.id'), nullable=False)
    duration = Column(Integer, nullable=False)

    date = Column(DateTime, default=datetime.datetime.now)

    user = orm.relationship('User', back_populates='activities')
    activity_type_rel = orm.relationship('ActivityType', back_populates='activities')

    def __repr__(self):
        return f'<Activity> {self.activity_type_rel.name} ({self.duration} min)'
