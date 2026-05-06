import asyncio
import os
from datetime import date, datetime, timedelta

from aiogram import Dispatcher, Bot, types, filters, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from data import db_session
from data.active_timers import ActiveTimer
from data.activites import Activity
from data.activity_types import ActivityType
from data.biometrics import Biometric
from data.users import User
from weather_api import get_current_weather, get_city_coordinates

load_dotenv()

MIN_AGE = 1
MAX_AGE = 123
MIN_HEIGHT = 50
MAX_HEIGHT = 272
MIN_WEIGHT = 20
MAX_WEIGHT = 500

LEVEL_THRESHOLDS = [
    0,  # Level 1: 0 минут
    60,  # Level 2: 1 час
    180,  # Level 3: 3 часа
    360,  # Level 4: 6 часов
    600,  # Level 5: 10 часов
    900,  # Level 6: 15 часов
    1500,  # Level 7: 25 часов
    2400,  # Level 8: 40 часов
    3600,  # Level 9: 60 часов
    6000,  # Level 10: 100 часов
    10000,  # Level 11: 167 часов
    15000,  # Level 12: 250 часов
    25000,  # Level 13: 417 часов
    40000,  # Level 14: 667 часов
    60000,  # Level 15: 1000 часов
]

LEVEL_TITLES = {
    1: "🌱 Новичок",
    2: "🏃 Начинающий",
    3: "💪 Любитель",
    4: "🎯 Энтузиаст",
    5: "⭐ Атлет",
    6: "🔥 Продвинутый",
    7: "⚡ Профессионал",
    8: "🌟 Эксперт",
    9: "💎 Мастер",
    10: "👑 Элита",
    11: "🦾 Титан",
    12: "🐉 Легенда",
    13: "🌌 Мифический",
    14: "⚜️ Бог фитнеса",
    15: "♾️ Абсолют",
}

active_timer_tasks = {}

TOKEN = os.getenv('TOKEN')
PROXY_URL = os.getenv('PROXY_URL', None)

if not TOKEN:
    raise ValueError(
        "Токен бота не найден!\n"
        "1. Создайте файл .env в корне проекта\n"
        "2. Добавьте строку: TOKEN=ваш_токен_от_BotFather\n"
        "3. Добавьте строку: PROXY_URL=http://ваш_прокси:порт (если нужно)\n"
        "4. Перезапустите бота"
    )

from aiogram import BaseMiddleware


class DeletedUserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = None
        text = None

        if isinstance(event, types.Message):
            user_id = event.from_user.id
            text = event.text
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
            text = event.data

        if user_id:
            if text and text.startswith('/start'):
                return await handler(event, data)

            async for session in db_session.create_async_session():
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()

                if user and user.is_deleted:  # а ведь можно забанить кого-то конкретного... а впрочем
                    msg = "❌ <b>Ваш аккаунт удален.</b>\nОтправьте /start для восстановления."

                    if isinstance(event, types.Message):
                        await event.answer(msg, reply_markup=types.ReplyKeyboardRemove())
                    elif isinstance(event, types.CallbackQuery):
                        await event.answer("❌ Аккаунт удален!", show_alert=True)
                        try:
                            await event.message.answer(msg, reply_markup=types.ReplyKeyboardRemove())
                        except TelegramBadRequest:
                            pass

                    return

        return await handler(event, data)


if PROXY_URL:
    print(f"🔒 Использую прокси: {PROXY_URL}")
    session = AiohttpSession(proxy=PROXY_URL)
else:
    print("⚠️ Прокси не указан. Пробую прямое подключение...")
    session = None

# Инициализация бота
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=session
)
dp = Dispatcher()


class BioStates(StatesGroup):
    waiting_for_age = State()
    waiting_for_height = State()
    waiting_for_weight = State()
    waiting_for_city = State()


class ActivityStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_duration = State()


class TimerStates(StatesGroup):
    waiting_for_activity_type = State()


### Менюшке

def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Биометрика")],
            [KeyboardButton(text="📝 Активности")],
            [KeyboardButton(text="⏱ Таймер тренировки")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🗑 Удаление данных")]
        ],
        resize_keyboard=True,
        is_persistent=True,

    )


def bio_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Возраст",
                                  callback_data="bio_age")],
            [InlineKeyboardButton(text="Рост",
                                  callback_data="bio_height")],
            [InlineKeyboardButton(text="Вес",
                                  callback_data="bio_weight")],
            [InlineKeyboardButton(text="Город",
                                  callback_data="bio_city")]
        ]
    )


def activities_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить активность",
                                  callback_data="act_add")],
            [InlineKeyboardButton(text="📋 Мой день (Просмотр/Удаление)",
                                  callback_data="act_view")]
        ]
    )


def timer_kb(is_active=False):
    if is_active:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏹ Остановить таймер",
                                      callback_data="timer_stop")],
            ]
        )
    else:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="▶️ Запустить таймер",
                                      callback_data="timer_start")],
            ]
        )


def stats_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Статистика за сегодня",
                                  callback_data="stats_today")],
            [InlineKeyboardButton(text="📊 Статистика за неделю",
                                  callback_data="stats_week")],
            [InlineKeyboardButton(text="📈 Статистика за месяц",
                                  callback_data="stats_month")],
            [InlineKeyboardButton(text="🎯 Общая статистика",
                                  callback_data="stats_all")],
            [InlineKeyboardButton(text="🔄 Сравнение по активностям",
                                  callback_data="stats_compare")]
        ]
    )


### Конец менюшке

# Система уровней
def calculate_level(total_minutes: int) -> tuple:
    level = 1
    next_threshold = LEVEL_THRESHOLDS[1] if len(LEVEL_THRESHOLDS) > 1 else float('inf')

    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_minutes >= threshold:
            level = i + 1
            next_threshold = LEVEL_THRESHOLDS[i + 1] if i + 1 < len(LEVEL_THRESHOLDS) else float('inf')
        else:
            next_threshold = threshold
            break

    title = LEVEL_TITLES.get(level, "🌱 Новичок")
    progress = total_minutes
    need_for_next = next_threshold - total_minutes if next_threshold != float('inf') else 0

    return level, title, progress, need_for_next


async def update_user_experience(user_id: int, minutes: int):
    async for session in db_session.create_async_session():
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalars().first()

        if user:
            user.total_minutes += minutes
            old_level = user.level
            user.level, _, _, _ = calculate_level(user.total_minutes)

            await session.commit()

            return user.level > old_level, user.level
    return False, 1


async def update_bio_db(user_id: int, field: str, value):
    async for session in db_session.create_async_session():
        result = await session.execute(
            select(Biometric).where(Biometric.user_id == user_id)
        )
        bio = result.scalars().first()

        if not bio:
            bio = Biometric(user_id=user_id, age=0, height=0, weight=0, city="Не указан")
            session.add(bio)

        if field == "age":
            bio.age = value
        elif field == "height":
            bio.height = value
        elif field == "weight":
            bio.weight = value
        elif field == "city":
            bio.city = value

        await session.commit()


@dp.message(filters.Command('start'))
async def cmd_start(message: types.Message):
    async for session in db_session.create_async_session():
        user_id = message.from_user.id
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        existing_user = result.scalars().first()

        if not existing_user:
            user_db = User(
                id=user_id,
                username=message.from_user.username
            )
            session.add(user_db)
            await session.commit()
            await message.answer(
                f"🎉 {message.from_user.first_name}, добро пожаловать в PyTracker!\n"
                f"Заполните данные о себе для продолжения.",
                reply_markup=main_kb()
            )
        elif existing_user.is_deleted:
            existing_user.is_deleted = False
            existing_user.username = message.from_user.username
            existing_user.registration_date = datetime.now()
            existing_user.level = 1
            existing_user.experience = 0
            existing_user.total_minutes = 0
            await session.commit()

            await message.answer(
                f"🎉 {message.from_user.first_name}, добро пожаловать обратно в PyTracker!\n"
                f"Ваш профиль был создан заново. Заполните данные о себе для продолжения.",
                reply_markup=main_kb()
            )
        else:
            await message.answer(
                f"👋 {message.from_user.first_name}, c возвращением!",
                reply_markup=main_kb()
            )


### БИОМЕТРИКА

@dp.message(F.text == "🏋️ Биометрика")
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
    elif action == "city":
        await state.set_state(BioStates.waiting_for_city)
        await callback.message.answer("Введите ваш город (например: Москва):")

    await callback.answer()


@dp.message(BioStates.waiting_for_city)
async def set_city(message: types.Message, state: FSMContext):
    city_name = message.text.strip()

    wait_msg = await message.answer("⏳ Ищу город в базе...")

    lat, lon, resolved_name = await get_city_coordinates(city_name)

    if lat is not None and lon is not None:
        await update_bio_db(message.from_user.id, "city", resolved_name)
        await wait_msg.edit_text(
            f"✅ Город успешно найден и сохранен: <b>{resolved_name}</b>!\nТеперь мы сможем показывать погоду.")
        await state.clear()
    else:
        await wait_msg.edit_text(
            "❌ Город не найден. Попробуйте написать название иначе (например, на английском языке или ближайший крупный город).")


@dp.message(BioStates.waiting_for_age)
async def set_age(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        age = int(message.text)
        if MIN_AGE <= age <= MAX_AGE:
            await update_bio_db(message.from_user.id, "age", age)
            await message.answer("✅ Возраст успешно сохранен!")
            await state.clear()
        else:
            await message.answer(f"❌ Пожалуйста, введите реальный возраст (от {MIN_AGE} до {MAX_AGE}).")
    else:
        await message.answer("❌ Пожалуйста, введите число.")


@dp.message(BioStates.waiting_for_height)
async def set_height(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        height = int(message.text)
        if MIN_HEIGHT <= height <= MAX_HEIGHT:
            await update_bio_db(message.from_user.id, "height", height)
            await message.answer("✅ Рост успешно сохранен!")
            await state.clear()
        else:
            await message.answer(f"❌ Пожалуйста, введите реальный рост (от {MIN_HEIGHT} до {MAX_HEIGHT} сантиметров).")
    else:
        await message.answer("❌ Пожалуйста, введите число.")


@dp.message(BioStates.waiting_for_weight)
async def set_weight(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        weight = int(message.text)
        if MIN_WEIGHT <= weight <= MAX_WEIGHT:
            await update_bio_db(message.from_user.id, "weight", weight)
            await message.answer("✅ Вес успешно сохранен!")
            await state.clear()
        else:
            await message.answer(f"❌ Пожалуйста, введите реальный вес (от {MIN_WEIGHT} до {MAX_WEIGHT} килограммов).")
    else:
        await message.answer("❌ Пожалуйста, введите число.")


### КОНЕЦ БИОМЕТРИКИ

### АКТИВНОСТЬ

@dp.message(F.text == "📝 Активности")
async def process_activities(message: types.Message):
    async for session in db_session.create_async_session():
        result = await session.execute(
            select(Biometric).where(Biometric.user_id == message.from_user.id)
        )
        bio = result.scalars().first()

        if not bio or bio.age == 0 or bio.height == 0 or bio.weight == 0:
            await message.answer("❌ Сначала заполните все данные в разделе 'Биометрика'!")
            return

        await message.answer("Меню активностей:",
                             reply_markup=activities_kb())


async def get_or_create_activity_type(session: AsyncSession, name: str):
    name = name.strip().lower()
    result = await session.execute(
        select(ActivityType).where(ActivityType.name.contains(name))
    )
    activity = result.scalars().first()

    if activity:
        return activity
    else:
        raise BaseException("Тип активности не найден")


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
        await message.answer("❌ Пожалуйста, введите число (минуты).")
        return

    duration = int(message.text)
    data = await state.get_data()

    async for session in db_session.create_async_session():
        try:
            activity_type = await get_or_create_activity_type(session, data['activity_type_input'])
            new_activity = Activity(
                user_id=message.from_user.id,
                activity_type_id=activity_type.id,
                duration=duration
            )

            session.add(new_activity)
            await session.commit()

            leveled_up, new_level = await update_user_experience(message.from_user.id, duration)

            response = f'✅ Активность "{activity_type.name}" ({duration} мин.) сохранена!'

            if leveled_up:
                level_title = LEVEL_TITLES.get(new_level, "")
                response += f'\n\n🎉 Поздравляем! Вы достигли {new_level} уровня - {level_title}!'

            await message.answer(response)
            await state.clear()

        except BaseException:
            await message.answer(
                f'❌ Данной активности не существует в базе данных.\n'
                f'Обратитесь к администратору бота для добавления!'
            )
            await state.clear()


@dp.callback_query(F.data == "act_view")
async def view_activities(callback: types.CallbackQuery):
    await callback.answer()

    async for session in db_session.create_async_session():
        today = date.today()

        result = await session.execute(
            select(Activity)
            .options(selectinload(Activity.activity_type_rel))
            .where(Activity.user_id == callback.from_user.id)
            .order_by(Activity.date.desc())
        )
        activities = result.scalars().all()

        today_acts = [a for a in activities if a.date.date() == today]

        if not today_acts:
            try:
                await callback.message.edit_text(
                    "📭 За сегодня активностей не было",
                    reply_markup=activities_kb()
                )
            except TelegramBadRequest:
                await callback.message.answer(
                    "📭 За сегодня активностей не было",
                    reply_markup=activities_kb()
                )
            return

        text = "📋 <b>Ваши активности за сегодня:</b>\n\n"
        buttons = []

        for a in today_acts:
            text += f"• {a.activity_type_rel.name} — {a.duration} мин.\n"
            buttons.append([InlineKeyboardButton(
                text=f"🗑 Удалить '{a.activity_type_rel.name}'",
                callback_data=f"act_del_{a.id}"
            )])

        buttons.append([InlineKeyboardButton(text="◀️ Назад",
                                             callback_data="act_back")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("act_del_"))
async def delete_activity(callback: types.CallbackQuery):
    act_id = int(callback.data.split("_")[2])

    async for session in db_session.create_async_session():
        result = await session.execute(
            select(Activity).where(
                Activity.id == act_id,
                Activity.user_id == callback.from_user.id
            )
        )
        act = result.scalars().first()

        if act:
            duration = act.duration
            await session.delete(act)

            user_result = await session.execute(
                select(User).where(User.id == callback.from_user.id)
            )
            user = user_result.scalars().first()
            if user:
                user.total_minutes = max(0, user.total_minutes - duration)
                user.level, _, _, _ = calculate_level(user.total_minutes)

            await session.commit()
            await callback.answer("✅ Активность удалена!")
            await view_activities(callback)
        else:
            await callback.answer("❌ Ошибка: активность не найдена.", show_alert=True)


@dp.callback_query(F.data == "act_back")
async def act_back(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(
            "Меню активностей:",
            reply_markup=activities_kb()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "Меню активностей:",
            reply_markup=activities_kb()
        )


### КОНЕЦ АКТИВНОСТИ

### ТАЙМЕР ТРЕНИРОВКИ

async def update_timer_message(user_id: int, chat_id: int, message_id: int, activity_type: str, start_time: datetime):
    """Обновляет сообщение таймера каждую секунду"""
    try:
        while True:
            if user_id not in active_timer_tasks:
                break

            now = datetime.now()
            elapsed = now - start_time

            total_seconds = int(elapsed.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            seconds_progress = seconds / 60 * 10
            bar_filled = int(seconds_progress)
            bar = "█" * bar_filled + "░" * (10 - bar_filled)

            timer_text = (
                f"⏱ <b>ТАЙМЕР АКТИВЕН</b>\n\n"
                f"🏃 Активность: <b>{activity_type}</b>\n"
                f"⏱ Время: <b>{hours:02d}:{minutes:02d}:{seconds:02d}</b>\n"
                f"[{bar}] {seconds}с\n\n"
                f"📅 Начало: {start_time.strftime('%H:%M:%S')}\n"
                f"🔄 Автообновление..."
            )

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=timer_text,
                    reply_markup=timer_kb(is_active=True)
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    print(f"Ошибка обновления таймера: {e}")
                    break
            except Exception as e:
                print(f"Ошибка таймера: {e}")
                break

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Таймер остановлен с ошибкой: {e}")
    finally:
        if user_id in active_timer_tasks:
            del active_timer_tasks[user_id]


@dp.message(F.text == "⏱ Таймер тренировки")
async def timer_menu(message: types.Message):
    async for session in db_session.create_async_session():
        result = await session.execute(
            select(ActiveTimer).where(
                ActiveTimer.user_id == message.from_user.id,
                ActiveTimer.is_active == True
            )
        )
        timer = result.scalars().first()

        is_active = timer is not None
        await message.answer("⏱ Управление таймером тренировки:",
                             reply_markup=timer_kb(is_active=is_active))


@dp.callback_query(F.data == "timer_start")
async def timer_start(callback: types.CallbackQuery, state: FSMContext):
    async for session in db_session.create_async_session():
        result = await session.execute(
            select(ActiveTimer).where(
                ActiveTimer.user_id == callback.from_user.id,
                ActiveTimer.is_active == True
            )
        )
        active_timer = result.scalars().first()

        if active_timer:
            elapsed = datetime.now() - active_timer.start_time
            time_str = str(elapsed).split('.')[0]

            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏹ Завершить текущий", callback_data="timer_stop")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_msg")]
            ])

            await callback.message.answer(
                f"⚠️ <b>У вас уже есть запущенный таймер!</b>\n\n"
                f"🏃 Активность: <b>{active_timer.activity_type}</b>\n"
                f"⏱ Прошло времени: <b>{time_str}</b>\n\n"
                f"Вы не можете запустить новый, пока не остановите текущий.",
                reply_markup=inline_kb,
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await state.set_state(TimerStates.waiting_for_activity_type)
        await callback.message.answer("Введите тип активности для отслеживания:")
        await callback.answer()


@dp.message(TimerStates.waiting_for_activity_type)
async def timer_set_type(message: types.Message, state: FSMContext):
    activity_type = message.text.strip().lower()
    user_id = message.from_user.id

    async for session in db_session.create_async_session():
        result = await session.execute(
            select(ActiveTimer).where(ActiveTimer.user_id == user_id)
        )
        timer = result.scalars().first()

        if timer and timer.is_active:
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏹ Завершить текущий", callback_data="timer_stop")]
            ])
            await message.answer("❌ Не удалось запустить: у вас уже активен другой таймер.",
                                 reply_markup=inline_kb)
            await state.clear()
            return

        act_type_res = await session.execute(
            select(ActivityType).where(ActivityType.name.contains(activity_type))
        )
        activity = act_type_res.scalars().first()

        if not activity:
            await message.answer("❌ Такой тип активности не найден. Попробуйте другое название.")
            return

        start_time = datetime.now()

        try:
            if timer:
                timer.activity_type = activity.name
                timer.start_time = start_time
                timer.is_active = True
            else:
                new_timer = ActiveTimer(
                    user_id=user_id,
                    activity_type=activity.name,
                    start_time=start_time,
                    is_active=True
                )
                session.add(new_timer)

            await session.commit()

        except Exception as e:
            await session.rollback()
            print(f"Ошибка при сохранении таймера: {e}")
            await message.answer("❌ Ошибка базы данных при запуске.")
            await state.clear()
            return

        timer_msg = await message.answer(
            f"⏱ <b>ТАЙМЕР ЗАПУЩЕН</b>\n\n"
            f"🏃 Активность: <b>{activity.name}</b>\n"
            f"⏱ Время: <b>00:00:00</b>\n"
            f"[░░░░░░░░░░] 0с\n\n"
            f"📅 Начало: {start_time.strftime('%H:%M:%S')}\n"
            f"🔄 Автообновление...",
            reply_markup=timer_kb(is_active=True)
        )

        task = asyncio.create_task(
            update_timer_message(
                user_id=user_id,
                chat_id=message.chat.id,
                message_id=timer_msg.message_id,
                activity_type=activity.name,
                start_time=start_time
            )
        )
        active_timer_tasks[user_id] = task
        await state.clear()


@dp.callback_query(F.data == "timer_stop")
async def timer_stop(callback: types.CallbackQuery):
    weather_text = ""
    user_id = callback.from_user.id

    if user_id in active_timer_tasks:
        task = active_timer_tasks[user_id]
        task.cancel()
        del active_timer_tasks[user_id]

    async for session in db_session.create_async_session():
        result = await session.execute(
            select(ActiveTimer).where(
                ActiveTimer.user_id == user_id,
                ActiveTimer.is_active == True
            )
        )
        timer = result.scalars().first()

        if not timer:
            await callback.answer("❌ Нет активного таймера!", show_alert=True)
            return

        elapsed = datetime.now() - timer.start_time
        total_seconds = int(elapsed.total_seconds())
        minutes = max(1, total_seconds // 60)
        hours = total_seconds // 3600
        remaining_seconds = total_seconds % 60

        act_result = await session.execute(
            select(ActivityType).where(ActivityType.name == timer.activity_type)
        )
        activity_type = act_result.scalars().first()

        if activity_type:
            new_activity = Activity(
                user_id=user_id,
                activity_type_id=activity_type.id,
                duration=minutes
            )
            session.add(new_activity)

            timer.is_active = False

            bio_result = await session.execute(
                select(Biometric).where(Biometric.user_id == user_id)
            )
            bio = bio_result.scalars().first()

            if bio and getattr(bio, 'city', None) and bio.city != "Не указан":
                lat, lon, _ = await get_city_coordinates(bio.city)
                if lat and lon:
                    weather_data = await get_current_weather(lat, lon)
                    if weather_data:
                        temp = weather_data.get('temperature')
                        weather_text = f"\n🌡️ Температура на тренировке: <b>{temp}°C</b>"

            await session.commit()

            leveled_up, new_level = await update_user_experience(user_id, minutes)

            time_str = f"{hours:02d}:{minutes % 60:02d}:{remaining_seconds:02d}"

            response = (
                f"⏹ <b>ТАЙМЕР ОСТАНОВЛЕН</b>\n\n"
                f"🏃 Активность: <b>{timer.activity_type}</b>\n"
                f"⏱ Длительность: <b>{time_str}</b>\n"
                f"📊 Зачтено минут: <b>{minutes} мин.</b>\n"
                f"📅 {timer.start_time.strftime('%H:%M:%S')} - {datetime.now().strftime('%H:%M:%S')}"
                f"{weather_text}"
            )

            if leveled_up:
                level_title = LEVEL_TITLES.get(new_level, "")
                response += f'\n\n🎉 Поздравляем! Вы достигли {new_level} уровня - {level_title}!'

            await callback.message.edit_text(
                response,
                reply_markup=timer_kb(is_active=False)
            )
        else:
            timer.is_active = False
            await session.commit()
            await callback.message.edit_text(
                "⏹ Таймер остановлен (тип активности не найден)",
                reply_markup=timer_kb(is_active=False)
            )

        await callback.answer("✅ Таймер остановлен!")


### КОНЕЦ ТАЙМЕРА

### ПРОФИЛЬ

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    async for session in db_session.create_async_session():
        user_result = await session.execute(
            select(User).where(User.id == message.from_user.id)
        )
        user = user_result.scalars().first()

        if not user:
            await message.answer("❌ Профиль не найден. Используйте /start")
            return

        bio_result = await session.execute(
            select(Biometric).where(Biometric.user_id == message.from_user.id)
        )
        bio = bio_result.scalars().first()

        level, title, progress, need_for_next = calculate_level(user.total_minutes)

        profile_text = f"👤 <b>Профиль пользователя</b>\n\n"
        profile_text += f"🆔 ID: <code>{user.id}</code>\n"
        profile_text += f"📅 Дата регистрации: {user.registration_date.strftime('%d.%m.%Y')}\n\n"

        profile_text += f"⭐ <b>Уровень: {level}</b> - {title}\n"

        bar_length = 10
        current_threshold = LEVEL_THRESHOLDS[level - 1] if level > 1 else 0
        next_threshold = LEVEL_THRESHOLDS[level] if level < len(LEVEL_THRESHOLDS) else float('inf')

        if next_threshold != float('inf'):
            progress_in_level = user.total_minutes - current_threshold
            level_range = next_threshold - current_threshold
            filled = int((progress_in_level / level_range) * bar_length)
            bar = "█" * filled + "░" * (bar_length - filled)
            profile_text += f"[{bar}] {progress_in_level}/{level_range} мин.\n"
        else:
            profile_text += f"[██████████] MAX LEVEL\n"

        profile_text += f"⏱ Всего минут: <b>{user.total_minutes}</b>\n"

        if need_for_next > 0:
            profile_text += f"📈 До следующего уровня: <b>{need_for_next} мин.</b>\n"

        stats_result = await session.execute(
            select(func.count(Activity.id)).where(Activity.user_id == message.from_user.id)
        )
        total_activities = stats_result.scalar()

        profile_text += f"🏃 Всего тренировок: <b>{total_activities or 0}</b>\n\n"

        if bio:
            profile_text += "<b>📊 Биометрика:</b>\n"
            profile_text += f"🎂 Возраст: {bio.age} лет\n"
            profile_text += f"📏 Рост: {bio.height} см\n"
            profile_text += f"⚖️ Вес: {bio.weight} кг\n"

            city = getattr(bio, 'city', 'Не указан')
            profile_text += f"🌍 Город: {city}\n"

            if bio.height > 0 and bio.weight > 0:
                height_m = bio.height / 100
                bmi = bio.weight / (height_m * height_m)
                profile_text += f"💪 ИМТ: {bmi:.1f} "

                if bmi < 18.5:
                    profile_text += "(Недостаточный вес)"
                elif bmi < 25:
                    profile_text += "(Норма)"
                elif bmi < 30:
                    profile_text += "(Избыточный вес)"
                else:
                    profile_text += "(Ожирение)"
        else:
            profile_text += "❌ Биометрика не заполнена"

        await message.answer(profile_text)


### КОНЕЦ ПРОФИЛЯ

### СТАТИСТИКА

@dp.message(F.text == "📊 Статистика")
async def process_statistics(message: types.Message):
    await message.answer("📊 Выберите период для просмотра статистики:",
                         reply_markup=stats_kb())


async def get_activities_summary(user_id: int, days: int = None, start_date: date = None):
    async for session in db_session.create_async_session():
        query = select(
            ActivityType.name,
            func.sum(Activity.duration).label('total_duration'),
            func.count(Activity.id).label('count')
        ).join(
            ActivityType, Activity.activity_type_id == ActivityType.id
        ).where(
            Activity.user_id == user_id
        )

        if days:
            start = date.today() - timedelta(days=days)
            query = query.where(Activity.date >= start)
        elif start_date:
            query = query.where(Activity.date >= start_date)

        query = query.group_by(ActivityType.name)

        result = await session.execute(query)
        return result.all()


async def get_total_stats(user_id: int, days: int = None, start_date: date = None):
    async for session in db_session.create_async_session():
        query = select(
            func.sum(Activity.duration).label('total_minutes'),
            func.count(Activity.id).label('total_activities')
        ).where(
            Activity.user_id == user_id
        )

        if days:
            start = date.today() - timedelta(days=days)
            query = query.where(Activity.date >= start)
        elif start_date:
            query = query.where(Activity.date >= start_date)

        result = await session.execute(query)
        return result.first()


def format_stats_message(period_name: str, activities, total_stats):
    if not total_stats or total_stats.total_minutes == 0:
        return f"📊 <b>Статистика за {period_name}</b>\n\n📭 Пока нет данных об активностях."

    hours = total_stats.total_minutes // 60
    minutes = total_stats.total_minutes % 60

    message = f"📊 <b>Статистика за {period_name}</b>\n\n"
    message += f"🏃 Всего активностей: <b>{total_stats.total_activities}</b>\n"

    if hours > 0:
        message += f"⏱ Общее время: <b>{hours} ч {minutes} мин</b>\n\n"
    else:
        message += f"⏱ Общее время: <b>{minutes} мин</b>\n\n"

    if activities:
        message += "<b>📋 По типам активностей:</b>\n"
        for name, total_duration, count in activities:
            act_hours = total_duration // 60
            act_minutes = total_duration % 60

            if act_hours > 0:
                message += f"• {name.title()}: {count} раз(а), {act_hours} ч {act_minutes} мин\n"
            else:
                message += f"• {name.title()}: {count} раз(а), {act_minutes} мин\n"

    return message


@dp.callback_query(F.data.startswith("stats_"))
async def stats_callback(callback: types.CallbackQuery):
    await callback.answer()

    action = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if action == "today":
        period_name = "сегодня"
        activities = await get_activities_summary(user_id, days=1)
        total_stats = await get_total_stats(user_id, days=1)

    elif action == "week":
        period_name = "неделю"
        activities = await get_activities_summary(user_id, days=7)
        total_stats = await get_total_stats(user_id, days=7)

    elif action == "month":
        period_name = "месяц"
        activities = await get_activities_summary(user_id, days=30)
        total_stats = await get_total_stats(user_id, days=30)

    elif action == "all":
        period_name = "всё время"
        activities = await get_activities_summary(user_id)
        total_stats = await get_total_stats(user_id)

    elif action == "compare":
        await show_compare_stats(callback)
        return

    elif action == "back":
        try:
            await callback.message.edit_text(
                "📊 Выберите период для просмотра статистики:",
                reply_markup=stats_kb()
            )
        except TelegramBadRequest:
            await callback.message.answer(
                "📊 Выберите период для просмотра статистики:",
                reply_markup=stats_kb()
            )
        return

    else:
        await callback.answer("❌ Неизвестная команда")
        return

    message = format_stats_message(period_name, activities, total_stats)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="stats_back")]
    ])

    try:
        await callback.message.edit_text(message, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("Данные не изменились")
        else:
            await callback.message.answer(message, reply_markup=keyboard)


async def show_compare_stats(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    week_activities = await get_activities_summary(user_id, days=7)
    week_total = await get_total_stats(user_id, days=7)

    month_activities = await get_activities_summary(user_id, days=30)
    month_total = await get_total_stats(user_id, days=30)

    message = "📊 <b>Сравнение активности</b>\n\n"

    if week_total and week_total.total_minutes:
        week_hours = week_total.total_minutes // 60
        week_mins = week_total.total_minutes % 60

        if week_hours > 0:
            message += f"📅 Неделя: <b>{week_total.total_activities}</b> активностей, <b>{week_hours} ч {week_mins} мин</b>\n"
        else:
            message += f"📅 Неделя: <b>{week_total.total_activities}</b> активностей, <b>{week_mins} мин</b>\n"

        if week_total.total_activities > 0:
            avg_week = week_total.total_minutes / week_total.total_activities
            message += f"   ⏱ Средняя длительность: <b>{avg_week:.1f} мин</b>\n"
    else:
        message += "📅 Неделя: нет данных\n"

    if month_total and month_total.total_minutes:
        month_hours = month_total.total_minutes // 60
        month_mins = month_total.total_minutes % 60

        if month_hours > 0:
            message += f"\n📆 Месяц: <b>{month_total.total_activities}</b> активностей, <b>{month_hours} ч {month_mins} мин</b>\n"
        else:
            message += f"\n📆 Месяц: <b>{month_total.total_activities}</b> активностей, <b>{month_mins} мин</b>\n"

        if month_total.total_activities > 0:
            avg_month = month_total.total_minutes / month_total.total_activities
            message += f"   ⏱ Средняя длительность: <b>{avg_month:.1f} мин</b>\n"

            daily_avg = month_total.total_minutes / 30
            message += f"   📊 Среднее в день: <b>{daily_avg:.1f} мин</b>\n"
    else:
        message += "\n📆 Месяц: нет данных\n"

    if month_activities:
        message += "\n🏆 <b>Топ активностей за месяц:</b>\n"
        sorted_activities = sorted(month_activities, key=lambda x: x.total_duration, reverse=True)
        for i, (name, duration, count) in enumerate(sorted_activities[:5], 1):
            hours = duration // 60
            mins = duration % 60
            if hours > 0:
                message += f"{i}. {name.title()}: {hours} ч {mins} мин\n"
            else:
                message += f"{i}. {name.title()}: {mins} мин\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="stats_back")]
    ])

    try:
        await callback.message.edit_text(message, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await callback.message.answer(message, reply_markup=keyboard)


@dp.callback_query(F.data == "stats_back")
async def stats_back(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(
            "📊 Выберите период для просмотра статистики:",
            reply_markup=stats_kb()
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await callback.message.answer(
                "📊 Выберите период для просмотра статистики:",
                reply_markup=stats_kb()
            )


### КОНЕЦ СТАТИСТИКИ

### УДАЛЕНИЕ ДАННЫХ

@dp.message(F.text == "🗑 Удаление данных")
async def delete_user_info(message: types.Message):
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить всё", callback_data="confirm_delete_all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
    ])

    await message.answer(
        "<b>⚠️ ВНИМАНИЕ! Необратимое действие!</b>\n\n"
        "Это удалит всю вашу историю активностей, биометрические данные и прогресс (уровни/минуты).\n"
        "Вы уверены, что хотите удалить свой профиль?",
        reply_markup=inline_kb
    )


@dp.callback_query(F.data == "confirm_delete_all")
async def process_delete_confirm(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    async for session in db_session.create_async_session():
        try:
            await session.execute(
                delete(ActiveTimer).where(ActiveTimer.user_id == user_id)
            )

            await session.execute(
                delete(Activity).where(Activity.user_id == user_id)
            )

            await session.execute(
                delete(Biometric).where(Biometric.user_id == user_id)
            )

            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            if user:
                user.is_deleted = True
                user.level = 1
                user.experience = 0
                user.total_minutes = 0

            await session.commit()

            if user_id in active_timer_tasks:
                active_timer_tasks[user_id].cancel()
                del active_timer_tasks[user_id]

            await callback.message.edit_text(
                "✅ Все ваши данные были успешно удалены. До свидания!\n\n"
                "<i>(Чтобы начать заново, отправьте команду /start)</i>",
                reply_markup=None
            )

        except Exception as e:
            await session.rollback()
            print(f"Ошибка при удалении данных пользователя {user_id}: {e}")
            await callback.answer("❌ Произошла ошибка базы данных при удалении.", show_alert=True)


@dp.callback_query(F.data == "cancel_delete")
async def process_delete_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("Удаление отменено. Продолжаем тренировки! 💪", reply_markup=None)
    await callback.answer()


### КОНЕЦ УДАЛЕНИЯ ДАННЫХ

@dp.message()
async def reply_me(message: types.Message):
    await message.answer(message.text)


async def main():
    from pathlib import Path

    db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
    Path(db_dir).mkdir(parents=True, exist_ok=True)

    db_path = os.path.join(db_dir, "tracker.db")
    print(f"📁 База данных: {db_path}")
    #
    # if os.path.exists(db_path):
    #     print("🗑 Удаляю старую базу данных...")
    #     os.remove(db_path)
    #
    db_session.global_init(db_path)
    print("✅ База данных инициализирована")

    async for session in db_session.create_async_session():
        default_activities = [
            "бег", "ходьба", "шаги", "турники", "отжимания",
            "приседания", "плавание", "велосипед", "тренажерный зал",
            "йога", "растяжка", "пресс", "скакалка"
        ]

        for act_name in default_activities:
            result = await session.execute(
                select(ActivityType).where(ActivityType.name == act_name)
            )
            existing = result.scalars().first()

            if not existing:
                session.add(ActivityType(name=act_name))
                print(f"  ➕ Добавлен тип активности: {act_name}")

        await session.commit()

    dp.message.middleware(DeletedUserMiddleware())
    dp.callback_query.middleware(DeletedUserMiddleware())

    print("🚀 Бот запущен!")

    try:
        await dp.start_polling(bot)
    finally:
        for task in active_timer_tasks.values():
            task.cancel()
        print("Бот остановлен, все таймеры отменены")


if __name__ == '__main__':
    asyncio.run(main())
