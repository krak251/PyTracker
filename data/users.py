import datetime
from sqlalchemy import Column, String, DateTime, BigInteger, orm, Boolean
from .db_session import SqlAlchemyBase


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    username = Column(String, nullable=True)

    registration_date = Column(DateTime, default=datetime.datetime.now)

    activities = orm.relationship('Activity', back_populates='user', cascade="all, delete-orphan")
    biometrics = orm.relationship('Biometric', back_populates='user', cascade="all, delete-orphan")

    is_deleted = Column(Boolean, default=False)

    def __repr__(self):
        return f'<User> {self.id} (@{self.username})'