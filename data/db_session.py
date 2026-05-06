import sqlalchemy as sa
import sqlalchemy.orm as orm
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import Session
import os
from pathlib import Path

SqlAlchemyBase = orm.declarative_base()

__factory = None
__async_factory = None


def global_init(db_file):
    global __factory, __async_factory

    # Если фабрики уже созданы, не инициализируем повторно
    if __factory and __async_factory:
        return

    if not db_file or not db_file.strip():
        raise Exception("Необходимо указать файл базы данных.")

    # Создаем директорию для БД, если её нет
    db_path = os.path.abspath(db_file.strip())
    db_dir = os.path.dirname(db_path)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)

    print(f"📁 Подключение к базе данных: {db_path}")

    # --- Настройка синхронного движка (нужен для создания таблиц) ---
    conn_str = f'sqlite:///{db_path}?check_same_thread=False'
    engine = sa.create_engine(conn_str, echo=False)
    __factory = orm.sessionmaker(bind=engine)

    # --- Настройка асинхронного движка (нужен для работы бота) ---
    async_conn_str = f'sqlite+aiosqlite:///{db_path}'
    async_engine = create_async_engine(async_conn_str, echo=False)
    __async_factory = orm.sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    # Импортируем модели, чтобы SqlAlchemy "узнала" о них перед созданием таблиц
    from . import __all_models

    # Создаем таблицы, если они еще не созданы (существующие данные не пострадают)
    SqlAlchemyBase.metadata.create_all(engine)
    print("✅ База данных готова к работе!")


def create_session() -> Session:
    global __factory
    if not __factory:
        raise Exception("Фабрика сессий не инициализирована. Вызовите global_init() сначала.")
    return __factory()


async def create_async_session():
    global __async_factory
    if not __async_factory:
        raise Exception("Асинхронная фабрика сессий не инициализирована. Вызовите global_init() сначала.")

    async with __async_factory() as session:
        yield session
