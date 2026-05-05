from aiogram import Dispatcher, Bot, types, filters, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
import os

from data import db_session
from data.users import User
from data.biometrics import Biometric
from data.activites import Activity

MIN_AGE = 1
MAX_AGE = 123
MIN_HEIGHT = 50
MAX_HEIGHT = 272
MIN_WEIGHT = 20
MAX_WEIGHT = 500

# сервера не буде, мне впадлу
load_dotenv()
bot = Bot(os.getenv('TOKEN'))
dp = Dispatcher()


class BioStates(StatesGroup):
    waiting_for_age = State()
    waiting_for_height = State()
    waiting_for_weight = State()


def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Биометрика")],
            [KeyboardButton(text="Активности")],
            [KeyboardButton(text="Статистика")],
            [KeyboardButton(text="Удаление данных")]
        ],
        resize_keyboard=True
    )


def bio_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Возраст",
                                  callback_data="bio_age")],
            [InlineKeyboardButton(text="Рост",
                                  callback_data="bio_height")],
            [InlineKeyboardButton(text="Вес",
                                  callback_data="bio_weight")]
        ]
    )


def update_bio_db(user_id: int, field: str, value: int):
    db = db_session.create_session()
    bio = db.query(Biometric).filter(Biometric.user_id == user_id).first()

    if not bio:
        bio = Biometric(user_id=user_id, age=0, height=0, weight=0)
        db.add(bio)

    if field == "age":
        bio.age = value
    elif field == "height":
        bio.height = value
    elif field == "weight":
        bio.weight = value

    db.commit()


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
        await message.answer(
            f"{message.from_user.first_name}, добро пожаловать в PyTracker!\nЗаполните данные о себе для продолжения.",
            reply_markup=main_kb()
        )
    else:
        await message.answer(
            f"{message.from_user.first_name}, c возвращением!",
            reply_markup=main_kb()
        )


@dp.message(F.text == "Биометрика")
async def bio_menu(message: types.Message):
    await message.answer("Выберите параметр для заполнения:", reply_markup=bio_kb())


@dp.callback_query(F.data.startswith("bio_"))
async def bio_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]

    if action == "age":
        await state.set_state(BioStates.waiting_for_age)
        await callback.message.answer("Введите ваш возраст (полных лет):")
    elif action == "height":
        await state.set_state(BioStates.waiting_for_height)
        await callback.message.answer("Введите ваш рост (в сантиметрах):")
    elif action == "weight":
        await state.set_state(BioStates.waiting_for_weight)
        await callback.message.answer("Введите ваш вес (в килограммах):")

    await callback.answer()


@dp.message(BioStates.waiting_for_age)
async def set_age(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        age = int(message.text)
        if MIN_AGE <= age <= MAX_AGE:
            update_bio_db(message.from_user.id, "age", age)
            await message.answer("Возраст успешно сохранен!")
            await state.clear()
        else:
            await message.answer(f"Пожалуйста, введите реальный возраст (от {MIN_AGE} до {MAX_AGE}).")
    else:
        await message.answer("Пожалуйста, введите число.")


@dp.message(BioStates.waiting_for_height)
async def set_height(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        height = int(message.text)
        if MIN_HEIGHT <= height <= MAX_HEIGHT:
            update_bio_db(message.from_user.id, "height", height)
            await message.answer("Рост успешно сохранен!")
            await state.clear()
        else:
            await message.answer(f"Пожалуйста, введите реальный рост (от {MIN_HEIGHT} до {MAX_HEIGHT} сантиметров).")
    else:
        await message.answer("Пожалуйста, введите число.")


@dp.message(BioStates.waiting_for_weight)
async def set_weight(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        weight = int(message.text)
        if MIN_WEIGHT <= weight <= MAX_WEIGHT:
            update_bio_db(message.from_user.id, "weight", weight)
            await message.answer("Вес успешно сохранен!")
            await state.clear()
        else:
            await message.answer(f"Пожалуйста, введите реальный вес (от {MIN_WEIGHT} до {MAX_WEIGHT} килограммов).")
    else:
        await message.answer("Пожалуйста, введите число.")


@dp.message(F.text == "Активности")
async def process_activities(message: types.Message):
    db = db_session.create_session()
    bio = db.query(Biometric).filter(Biometric.user_id == message.from_user.id).first()

    if not bio or bio.age == 0 or bio.height == 0 or bio.weight == 0:  # чем проще выглядит код тем лучше он исполняет свою функцию @Сунь Цзы искусство говнокода
        await message.answer("Сначала заполните все данные в разделе 'Биометрика'!")
        return

    await message.answer("WIP")


@dp.message(F.text == "Статистика")
async def process_statistics(message: types.Message):
    await message.answer("WIP")


@dp.message(F.text == "Удаление данных")
async def delete_user_info(message: types.Message):
    await message.answer("WIP")


@dp.message()
async def reply_me(message: types.Message):
    await message.answer(message.text)


async def main():
    db_session.global_init("db/tracker.db")
    print("бот запущен")
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())