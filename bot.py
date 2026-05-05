from aiogram import Dispatcher, Bot, types, filters, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
import os

from data import db_session
from data.users import User
from data.biometrics import Biometric
from data.activites import Activity
from data.activity_types import ActivityType

from datetime import date

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


class ActivityStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_duration = State()


### Менюшке

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


def activities_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить активность",
                                  callback_data="act_add")],
            [InlineKeyboardButton(text="Мой день (Просмотр/Удаление)",
                                  callback_data="act_view")]
        ]
    )


### Конец менюшке

def update_bio_db(user_id: int, field: str, value: int):
    db = db_session.create_session()
    bio = db.query(Biometric).filter(Biometric.user_id == user_id).first()

    if not bio:
        bio = Biometric(user_id=user_id,
                        age=0,
                        height=0,
                        weight=0)
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


### БИОМЕТРИКА

@dp.message(F.text == "Биометрика")
async def bio_menu(message: types.Message):
    await message.answer("Выберите параметр для заполнения:",
                         reply_markup=bio_kb())


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


### КОНЕЦ БИОМЕТРИКИ

### АКТИВНОСТЬ

@dp.message(F.text == "Активности")
async def process_activities(message: types.Message):
    db = db_session.create_session()
    bio = db.query(Biometric).filter(Biometric.user_id == message.from_user.id).first()

    if not bio or bio.age == 0 or bio.height == 0 or bio.weight == 0:
        await message.answer("Сначала заполните все данные в разделе 'Биометрика'!")
        return

    await message.answer("Меню активностей:",
                         reply_markup=activities_kb())


def get_or_create_activity_type(db, name: str):
    name = name.strip().lower()

    activity = db.query(ActivityType).filter(
        ActivityType.name.ilike(f"%{name.lower()}%")
    ).first()

    if activity:
        return activity

    else:
        return BaseException


@dp.callback_query(F.data == "act_add")
async def add_activity_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ActivityStates.waiting_for_type)
    await callback.message.answer("Введите тип активности (например: Бег, Шаги, Турники):")
    await callback.answer()


@dp.message(ActivityStates.waiting_for_type)
async def add_activity_type(message: types.Message, state: FSMContext):
    await state.update_data(activity_type_input=message.text)
    await state.set_state(ActivityStates.waiting_for_duration)
    await message.answer("Сколько минут длилась активность?")


@dp.message(ActivityStates.waiting_for_duration)
async def add_activity_duration(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число (минуты).")
        return

    duration = int(message.text)
    data = await state.get_data()

    db = db_session.create_session()

    try:
        activity_type = get_or_create_activity_type(db, data['activity_type_input'])
        new_activity = Activity(
            user_id=message.from_user.id,
            activity_type_id=activity_type.id,
            duration=duration
        )

        db.add(new_activity)
        db.commit()
        await message.answer(
            f'Активность "{activity_type.name}" ({duration} мин.) сохранена!'
        )

        await state.clear()

    except BaseException:
        await message.answer(
            f'Данной активности не существует в базе данных, обратитесь к администратору бота для добавления!'
        )

        await state.clear()

@dp.callback_query(F.data == "act_view")
async def view_activities(callback: types.CallbackQuery):
    db = db_session.create_session()
    activities = db.query(Activity).filter(Activity.user_id == callback.from_user.id).all()

    today_acts = []

    for activity in activities:
        if activity.date.date() == date.today():
            today_acts.append(activity)

    if not today_acts:
        await callback.answer()
        try:
            await callback.message.edit_text(
                "За сегодня активностей не было",
                reply_markup=activities_kb()
            )
            return
        except TelegramBadRequest:
            return


    text = "Ваши активности за сегодня:\n\n"
    buttons = []

    for a in today_acts:
        text += f"• {a.activity_type_rel.name} — {a.duration} мин.\n"
        buttons.append([InlineKeyboardButton(text=f"Удалить '{a.activity_type_rel.name}'",
                                             callback_data=f"act_del_{a.id}")])

    buttons.append([InlineKeyboardButton(text="Назад",
                                         callback_data="act_back")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("act_del_"))
async def delete_activity(callback: types.CallbackQuery):
    act_id = int(callback.data.split("_")[2])
    db = db_session.create_session()

    act = db.query(Activity).filter(Activity.id == act_id, Activity.user_id == callback.from_user.id).first()

    if act:
        db.delete(act)
        db.commit()
        await callback.answer("Активность удалена!")
        await view_activities(callback)
    else:
        await callback.answer("Ошибка: активность не найдена.", show_alert=True)


@dp.callback_query(F.data == "act_back")
async def act_back(callback: types.CallbackQuery):
    await callback.message.edit_text("Меню активностей:", reply_markup=activities_kb())


### КОНЕЦ АКТИВНОСТИ

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
