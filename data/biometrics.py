import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, BigInteger, orm
from .db_session import SqlAlchemyBase


class Biometric(SqlAlchemyBase):
    __tablename__ = 'biometrics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))

    age = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    weight = Column(Integer, nullable=False)

    date = Column(DateTime, default=datetime.datetime.now)

    user = orm.relationship('User', back_populates='biometrics')

    def __repr__(self):
        return f'<Biometric> {self.parameter_type}: {self.value}'

