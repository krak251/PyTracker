from aiogram import Dispatcher, Bot, types, filters

from dotenv import load_dotenv
import os


#здесь будет взаимодейтсвие бота с пользователем, а так же запросы к серверу
#если он конечно будет существовать.(не делать же всё в 1 файле)

load_dotenv()
bot = Bot(os.getenv('TOKEN'))
dp = Dispatcher(bot=bot)


@dp.message(filters.Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(f"{message.from_user.first_name}, привет!")

@dp.message()
async def reply_me(message:types.Message):
    await message.answer(message.text)

async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
