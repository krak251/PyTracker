import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger, orm, Boolean
from .db_session import SqlAlchemyBase


class ActiveTimer(SqlAlchemyBase):
    __tablename__ = 'active_timers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), unique=True)
    activity_type = Column(String, nullable=False)
    start_time = Column(DateTime, default=datetime.datetime.now)
    is_active = Column(Boolean, default=True)

    user = orm.relationship('User')

    def __repr__(self):
        return f'<ActiveTimer> User: {self.user_id} - {self.activity_type}'