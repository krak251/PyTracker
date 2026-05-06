import sqlalchemy as sa
import sqlalchemy.orm as orm
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import Session
import asyncio
import os
from pathlib import Path

SqlAlchemyBase = orm.declarative_base()

__factory = None
__async_factory = None


def global_init(db_file):
    global __factory, __async_factory

    if __factory and __async_factory:
        return

    if not db_file or not db_file.strip():
        raise Exception("Необходимо указать файл базы данных.")

    db_dir = os.path.dirname(db_file)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)

    db_path = os.path.abspath(db_file)
    db_exists = os.path.exists(db_path)

    if db_exists:
        print(f"🗑 Удаляю старую базу данных: {db_path}")
        os.remove(db_path)
        print("✅ Старая БД удалена")

    print(f"📁 Создаю новую базу данных: {db_path}")

    conn_str = f'sqlite:///{db_path}?check_same_thread=False'
    print(f"Подключение к базе данных по адресу {conn_str}")

    engine = sa.create_engine(conn_str, echo=False)
    __factory = orm.sessionmaker(bind=engine)

    async_conn_str = f'sqlite+aiosqlite:///{db_path}'
    async_engine = create_async_engine(async_conn_str, echo=False)
    __async_factory = orm.sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    from . import __all_models

    SqlAlchemyBase.metadata.create_all(engine)
    print("✅ База данных успешно создана!")


def create_session() -> Session:
    global __factory
    return __factory()


async def create_async_session():
    global __async_factory
    async with __async_factory() as session:
        yield session