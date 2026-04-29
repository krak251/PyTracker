from aiogram import Dispatcher, Bot, types, filters

from dotenv import load_dotenv
import os

from data import db_session
from data.users import User

#здесь будет взаимодейтсвие бота с пользователем, а так же запросы к серверу
#если он конечно будет существовать.(не делать же всё в 1 файле)

load_dotenv()
bot = Bot(os.getenv('TOKEN'))
dp = Dispatcher()


@dp.message(filters.Command('start'))
async def cmd_start(message: types.Message):

    db = db_session.create_session()

    user = message.from_user
    if not db.query(User).filter(User.id == user.id).first():
        user_db = User(
            id=user.id,
            username=user.username
        )
        db.add(user_db)
        db.commit()
        await message.answer(f"{message.from_user.first_name}, добро пожаловать в PyTracker!")
    else:
        await message.answer(f"{message.from_user.first_name}, c возвращением!")

@dp.message()
async def reply_me(message:types.Message):
    await message.answer(message.text)


async def main():
    db_session.global_init("db/tracker.db")

    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())