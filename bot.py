import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from states import Registration, EditProfile
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8455223149:AAF4eBAnW9-z96rpY5fU4ceSoLK4F7tZTf4")
# ID администратора — замените на свой Telegram ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "1697156984"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database("dating.db")


# ─── KEYBOARDS ───────────────────────────────────────────────────────────────

def kb_gender():
    builder = InlineKeyboardBuilder()
    builder.button(text="👨 Мужчина", callback_data="gender_male")
    builder.button(text="👩 Женщина", callback_data="gender_female")
    builder.adjust(2)
    return builder.as_markup()

def kb_looking_for():
    builder = InlineKeyboardBuilder()
    builder.button(text="👨 Парней", callback_data="look_male")
    builder.button(text="👩 Девушек", callback_data="look_female")
    builder.button(text="👥 Всех", callback_data="look_any")
    builder.adjust(3)
    return builder.as_markup()

def kb_goals():
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Серьёзные отношения", callback_data="goal_serious")
    builder.button(text="😊 Лёгкое общение", callback_data="goal_casual")
    builder.button(text="🤝 Дружба", callback_data="goal_friendship")
    builder.button(text="🎯 Совместные интересы", callback_data="goal_hobbies")
    builder.adjust(2)
    return builder.as_markup()

def kb_profile_actions():
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Лайк", callback_data="swipe_like")
    builder.button(text="👎 Пропуск", callback_data="swipe_skip")
    builder.adjust(2)
    return builder.as_markup()

def kb_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔍 Смотреть анкеты")
    builder.button(text="👤 Моя анкета")
    builder.button(text="✏️ Редактировать анкету")
    builder.button(text="⏸ Пауза / ▶️ Продолжить")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def kb_edit_profile():
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Имя", callback_data="edit_name")
    builder.button(text="🎂 Возраст", callback_data="edit_age")
    builder.button(text="🏙 Город", callback_data="edit_city")
    builder.button(text="🎯 Цель", callback_data="edit_goal")
    builder.button(text="📖 О себе", callback_data="edit_bio")
    builder.button(text="🖼 Фото", callback_data="edit_photo")
    builder.button(text="🔢 Возрастной фильтр", callback_data="edit_age_filter")
    builder.adjust(2)
    return builder.as_markup()

def kb_moderate_user(user_id: int):
    """Admin buttons for new profile moderation."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"mod_approve_{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"mod_reject_{user_id}")
    builder.adjust(2)
    return builder.as_markup()

def kb_moderate_edit(edit_id: int):
    """Admin buttons for edit moderation."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"edit_approve_{edit_id}")
    builder.button(text="❌ Отклонить", callback_data=f"edit_reject_{edit_id}")
    builder.adjust(2)
    return builder.as_markup()

GOALS_TEXT = {
    "serious": "❤️ Серьёзные отношения",
    "casual": "😊 Лёгкое общение",
    "friendship": "🤝 Дружба",
    "hobbies": "🎯 Совместные интересы",
}

GENDER_TEXT = {"male": "👨 Мужчина", "female": "👩 Женщина"}

EDIT_FIELD_NAMES = {
    "bio": "📖 О себе",
    "photo_id": "🖼 Фото",
    "name": "📝 Имя",
    "age": "🎂 Возраст",
    "city": "🏙 Город",
    "goal": "🎯 Цель",
}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def format_profile(user: dict, show_filter: bool = False) -> str:
    goal = GOALS_TEXT.get(user["goal"], user["goal"])
    gender = GENDER_TEXT.get(user["gender"], user["gender"])
    bio = user.get("bio") or "—"
    text = (
        f"👤 <b>{user['name']}</b>, {user['age']} лет\n"
        f"{gender} · 🏙 {user['city']}\n"
        f"🎯 Цель: {goal}\n"
        f"📖 {bio}"
    )
    if show_filter:
        age_min = user.get("age_min", 18)
        age_max = user.get("age_max", 99)
        text += f"\n🔢 Ищу: {age_min}–{age_max} лет"
    return text

async def send_profile(chat_id: int, user: dict, markup=None, show_filter: bool = False):
    text = format_profile(user, show_filter=show_filter)
    photo = user.get("photo_id")
    if photo:
        await bot.send_photo(chat_id, photo, caption=text, parse_mode="HTML", reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

async def show_next_profile(message_or_call, user_id: int):
    candidate = db.get_next_candidate(user_id)
    chat_id = message_or_call.from_user.id if hasattr(message_or_call, "from_user") else message_or_call.message.chat.id

    if not candidate:
        await bot.send_message(chat_id, "😔 Анкеты закончились. Загляни позже!", reply_markup=kb_main_menu())
        return

    await send_profile(chat_id, candidate, markup=kb_profile_actions())

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ─── SEND PROFILE TO ADMIN FOR MODERATION ────────────────────────────────────

async def send_to_admin_for_moderation(user: dict):
    """Send new profile to admin with Approve/Reject buttons."""
    text = (
        f"🆕 <b>Новая анкета на модерации</b>\n\n"
        f"{format_profile(user)}\n\n"
        f"👤 ID: <code>{user['user_id']}</code>\n"
        f"@{user.get('username') or '—'}"
    )
    photo = user.get("photo_id")
    markup = kb_moderate_user(user["user_id"])
    try:
        if photo:
            await bot.send_photo(ADMIN_ID, photo, caption=text, parse_mode="HTML", reply_markup=markup)
        else:
            await bot.send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Не удалось отправить анкету админу: {e}")

async def send_edit_to_admin(user: dict, field: str, new_value: str, edit_id: int):
    """Notify admin about a profile edit that needs moderation."""
    field_name = EDIT_FIELD_NAMES.get(field, field)
    text = (
        f"✏️ <b>Правка анкеты на модерации</b>\n\n"
        f"Пользователь: <b>{user['name']}</b> (ID: <code>{user['user_id']}</code>)\n"
        f"Поле: {field_name}\n"
    )
    markup = kb_moderate_edit(edit_id)
    try:
        if field == "photo_id" and new_value:
            await bot.send_photo(
                ADMIN_ID, new_value,
                caption=text + "↑ Новое фото",
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            display = GOALS_TEXT.get(new_value, new_value) if field == "goal" else new_value
            await bot.send_message(
                ADMIN_ID,
                text + f"Новое значение: <b>{display or '(пусто)'}</b>",
                parse_mode="HTML",
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Не удалось отправить правку админу: {e}")


# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    existing = db.get_user(user_id)

    if existing:
        status = existing.get("status", "approved")
        if status == "pending":
            await message.answer(
                f"👋 С возвращением, <b>{existing['name']}</b>!\n\n"
                "⏳ Твоя анкета пока на модерации. Мы уведомим тебя, как только она будет проверена.",
                parse_mode="HTML"
            )
        elif status == "rejected":
            await message.answer(
                f"👋 С возвращением, <b>{existing['name']}</b>!\n\n"
                "❌ К сожалению, твоя анкета была отклонена модератором.\n"
                "Напиши /new_profile чтобы создать анкету заново.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"👋 С возвращением, <b>{existing['name']}</b>!\nЧто будем делать?",
                parse_mode="HTML",
                reply_markup=kb_main_menu()
            )
        return

    await message.answer(
        "👋 Привет! Это бот знакомств.\n\nДавай создадим твою анкету.\n\n<b>Как тебя зовут?</b>",
        parse_mode="HTML"
    )
    await state.set_state(Registration.name)


@dp.message(Command("new_profile"))
async def cmd_new_profile(message: Message, state: FSMContext):
    """Allow rejected users to re-register."""
    user = db.get_user(message.from_user.id)
    if user and user.get("status") != "rejected":
        await message.answer("У тебя уже есть активная или ожидающая проверки анкета.")
        return
    await message.answer("Давай создадим новую анкету.\n\n<b>Как тебя зовут?</b>", parse_mode="HTML")
    await state.set_state(Registration.name)


# ─── REGISTRATION FSM ────────────────────────────────────────────────────────

@dp.message(Registration.name)
async def reg_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 30:
        await message.answer("Имя должно быть от 2 до 30 символов. Попробуй ещё раз:")
        return
    await state.update_data(name=name)
    await message.answer(f"Отлично, <b>{name}</b>! 🎉\n\n<b>Сколько тебе лет?</b>", parse_mode="HTML")
    await state.set_state(Registration.age)

@dp.message(Registration.age)
async def reg_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if age < 18 or age > 99:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный возраст (18–99):")
        return
    await state.update_data(age=age)
    await message.answer("Выбери свой пол:", reply_markup=kb_gender())
    await state.set_state(Registration.gender)

@dp.callback_query(Registration.gender, F.data.startswith("gender_"))
async def reg_gender(call: CallbackQuery, state: FSMContext):
    gender = call.data.replace("gender_", "")
    await state.update_data(gender=gender)
    await call.message.edit_text("Кого ты хочешь найти?", reply_markup=kb_looking_for())
    await state.set_state(Registration.looking_for)

@dp.callback_query(Registration.looking_for, F.data.startswith("look_"))
async def reg_looking_for(call: CallbackQuery, state: FSMContext):
    looking_for = call.data.replace("look_", "")
    await state.update_data(looking_for=looking_for)
    await call.message.edit_text(
        "🔢 Укажи <b>минимальный</b> возраст для поиска (например: 18):",
        parse_mode="HTML"
    )
    await state.set_state(Registration.age_min)

@dp.message(Registration.age_min)
async def reg_age_min(message: Message, state: FSMContext):
    try:
        age_min = int(message.text.strip())
        if age_min < 18 or age_min > 99:
            raise ValueError
    except ValueError:
        await message.answer("Введи число от 18 до 99:")
        return
    await state.update_data(age_min=age_min)
    await message.answer(
        f"🔢 Теперь <b>максимальный</b> возраст (не меньше {age_min}, например: 35):",
        parse_mode="HTML"
    )
    await state.set_state(Registration.age_max)

@dp.message(Registration.age_max)
async def reg_age_max(message: Message, state: FSMContext):
    data = await state.get_data()
    age_min = data.get("age_min", 18)
    try:
        age_max = int(message.text.strip())
        if age_max < age_min or age_max > 99:
            raise ValueError
    except ValueError:
        await message.answer(f"Введи число от {age_min} до 99:")
        return
    await state.update_data(age_max=age_max)
    await message.answer("🏙 В каком городе ты живёшь?\n\nНапиши название города:")
    await state.set_state(Registration.city)

@dp.message(Registration.city)
async def reg_city(message: Message, state: FSMContext):
    city = message.text.strip().title()
    if len(city) < 2:
        await message.answer("Введи название города:")
        return
    await state.update_data(city=city)
    await message.answer("Какова твоя цель знакомства?", reply_markup=kb_goals())
    await state.set_state(Registration.goal)

@dp.callback_query(Registration.goal, F.data.startswith("goal_"))
async def reg_goal(call: CallbackQuery, state: FSMContext):
    goal = call.data.replace("goal_", "")
    await state.update_data(goal=goal)
    await call.message.edit_text("📖 Расскажи немного о себе (или нажми /skip чтобы пропустить):")
    await state.set_state(Registration.bio)

@dp.message(Registration.bio, Command("skip"))
@dp.message(Registration.bio)
async def reg_bio(message: Message, state: FSMContext):
    bio = None if message.text == "/skip" else message.text.strip()[:300]
    await state.update_data(bio=bio)
    await message.answer("🖼 Отправь своё фото (или /skip чтобы без фото):")
    await state.set_state(Registration.photo)

@dp.message(Registration.photo, Command("skip"))
@dp.message(Registration.photo, F.photo)
async def reg_photo(message: Message, state: FSMContext):
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)

    data = await state.get_data()
    user_id = message.from_user.id

    db.create_user(
        user_id=user_id,
        name=data["name"],
        age=data["age"],
        gender=data["gender"],
        looking_for=data["looking_for"],
        city=data["city"],
        goal=data["goal"],
        bio=data.get("bio"),
        photo_id=photo_id,
        username=message.from_user.username,
        age_min=data.get("age_min", 18),
        age_max=data.get("age_max", 99),
    )
    await state.clear()

    user = db.get_user(user_id)
    await message.answer("✅ Анкета отправлена на модерацию!\n\nВот как она выглядит:")
    await send_profile(message.chat.id, user)
    await message.answer(
        "⏳ Ожидай проверки от администратора. Мы уведомим тебя о результате.",
        reply_markup=kb_main_menu()
    )

    # Notify admin
    await send_to_admin_for_moderation(user)

@dp.message(Registration.photo)
async def reg_photo_wrong(message: Message):
    await message.answer("Пожалуйста, отправь фото или напиши /skip")


# ─── ADMIN: MODERATION ────────────────────────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    pending_profiles = db.get_pending_users()
    pending_edits = db.get_pending_edits()
    text = (
        f"🛡 <b>Панель администратора</b>\n\n"
        f"⏳ Анкет на проверке: <b>{len(pending_profiles)}</b>\n"
        f"✏️ Правок на проверке: <b>{len(pending_edits)}</b>"
    )
    builder = InlineKeyboardBuilder()
    if pending_profiles:
        builder.button(text=f"📋 Показать анкеты ({len(pending_profiles)})", callback_data="admin_show_pending")
    if pending_edits:
        builder.button(text=f"✏️ Показать правки ({len(pending_edits)})", callback_data="admin_show_edits")
    builder.adjust(1)
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup() if pending_profiles or pending_edits else None)

@dp.callback_query(F.data == "admin_show_pending")
async def admin_show_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pending = db.get_pending_users()
    if not pending:
        await call.answer("Нет анкет на проверке")
        return
    await call.answer()
    for user in pending:
        await send_to_admin_for_moderation(user)

@dp.callback_query(F.data == "admin_show_edits")
async def admin_show_edits(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    edits = db.get_pending_edits()
    if not edits:
        await call.answer("Нет правок на проверке")
        return
    await call.answer()
    for edit in edits:
        user = db.get_user(edit["user_id"])
        if user:
            await send_edit_to_admin(user, edit["field"], edit["new_value"], edit["id"])

# ── Approve / Reject new profile ──

@dp.callback_query(F.data.startswith("mod_approve_"))
async def mod_approve(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.replace("mod_approve_", ""))
    db.approve_user(user_id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ Одобрено")
    await call.message.reply(f"✅ Анкета пользователя {user_id} одобрена.")
    # Notify user
    try:
        await bot.send_message(
            user_id,
            "🎉 Твоя анкета прошла модерацию и теперь активна!\n\nМожешь начинать знакомиться 🚀",
            reply_markup=kb_main_menu()
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

@dp.callback_query(F.data.startswith("mod_reject_"))
async def mod_reject(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.replace("mod_reject_", ""))
    db.reject_user(user_id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Отклонено")
    await call.message.reply(f"❌ Анкета пользователя {user_id} отклонена.")
    try:
        await bot.send_message(
            user_id,
            "😔 Твоя анкета не прошла модерацию.\n\n"
            "Напиши /new_profile чтобы создать анкету заново и учесть замечания."
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

# ── Approve / Reject edit ──

@dp.callback_query(F.data.startswith("edit_approve_"))
async def edit_approve(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    edit_id = int(call.data.replace("edit_approve_", ""))
    edit = db.get_pending_edit(edit_id)
    if not edit:
        await call.answer("Правка не найдена (уже обработана?)")
        return
    # Apply the edit
    db.update_user(edit["user_id"], **{edit["field"]: edit["new_value"]})
    db.delete_pending_edit(edit_id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ Правка принята")
    field_name = EDIT_FIELD_NAMES.get(edit["field"], edit["field"])
    try:
        await bot.send_message(
            edit["user_id"],
            f"✅ Твоя правка поля «{field_name}» одобрена и применена!",
            reply_markup=kb_main_menu()
        )
    except Exception as e:
        logger.error(e)

@dp.callback_query(F.data.startswith("edit_reject_"))
async def edit_reject(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    edit_id = int(call.data.replace("edit_reject_", ""))
    edit = db.get_pending_edit(edit_id)
    if not edit:
        await call.answer("Правка не найдена")
        return
    db.delete_pending_edit(edit_id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Правка отклонена")
    field_name = EDIT_FIELD_NAMES.get(edit["field"], edit["field"])
    try:
        await bot.send_message(
            edit["user_id"],
            f"❌ Твоя правка поля «{field_name}» была отклонена модератором."
        )
    except Exception as e:
        logger.error(e)


# ─── MAIN MENU ───────────────────────────────────────────────────────────────

def _check_approved(user) -> str | None:
    """Returns error message if user can't browse, else None."""
    if not user:
        return "Сначала создай анкету — /start"
    status = user.get("status", "approved")
    if status == "pending":
        return "⏳ Твоя анкета ещё на модерации. Ожидай уведомления."
    if status == "rejected":
        return "❌ Твоя анкета была отклонена. Напиши /new_profile чтобы создать новую."
    return None

@dp.message(F.text == "🔍 Смотреть анкеты")
async def browse_profiles(message: Message):
    user = db.get_user(message.from_user.id)
    err = _check_approved(user)
    if err:
        await message.answer(err)
        return
    if user.get("is_paused"):
        await message.answer("Ты на паузе. Нажми «⏸ Пауза / ▶️ Продолжить» чтобы возобновить поиск.")
        return
    await show_next_profile(message, message.from_user.id)

@dp.message(F.text == "👤 Моя анкета")
async def my_profile(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала создай анкету — /start")
        return
    status = user.get("status", "approved")
    status_label = {"pending": "⏳ На модерации", "approved": "✅ Активна", "rejected": "❌ Отклонена"}.get(status, status)
    await send_profile(message.chat.id, user, markup=kb_edit_profile(), show_filter=True)
    await message.answer(f"Статус анкеты: {status_label}")

@dp.message(F.text == "⏸ Пауза / ▶️ Продолжить")
async def toggle_pause(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала создай анкету — /start")
        return
    paused = not user.get("is_paused", False)
    db.update_user(message.from_user.id, is_paused=int(paused))
    if paused:
        await message.answer("⏸ Поиск приостановлен. Твоя анкета скрыта.", reply_markup=kb_main_menu())
    else:
        await message.answer("▶️ Поиск возобновлён! Анкета снова видна.", reply_markup=kb_main_menu())

@dp.message(F.text == "✏️ Редактировать анкету")
async def edit_profile_menu(message: Message):
    await message.answer("Что хочешь изменить?", reply_markup=kb_edit_profile())


# ─── SWIPES ──────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "swipe_like")
async def swipe_like(call: CallbackQuery):
    user_id = call.from_user.id
    target_id = db.get_last_shown(user_id)
    if not target_id:
        await call.answer("Что-то пошло не так")
        return

    db.add_like(user_id, target_id)
    await call.answer("❤️ Лайк!")

    if db.is_mutual_like(user_id, target_id):
        me = db.get_user(user_id)
        them = db.get_user(target_id)

        match_text_me = (
            f"🎉 <b>Взаимная симпатия!</b>\n\n"
            f"Тебе понравился(ась) <b>{them['name']}</b> — и он(а) тоже!\n"
            f"👉 @{them.get('username') or 'пользователь'} (ID: {target_id})"
        )
        match_text_them = (
            f"🎉 <b>Взаимная симпатия!</b>\n\n"
            f"Тебе понравился(ась) <b>{me['name']}</b> — и он(а) тоже!\n"
            f"👉 @{me.get('username') or 'пользователь'} (ID: {user_id})"
        )

        await bot.send_message(user_id, match_text_me, parse_mode="HTML")
        await bot.send_message(target_id, match_text_them, parse_mode="HTML")

    await call.message.delete()
    await show_next_profile(call, user_id)

@dp.callback_query(F.data == "swipe_skip")
async def swipe_skip(call: CallbackQuery):
    user_id = call.from_user.id
    target_id = db.get_last_shown(user_id)
    if target_id:
        db.add_skip(user_id, target_id)
    await call.answer("👎 Пропуск")
    await call.message.delete()
    await show_next_profile(call, user_id)


# ─── EDIT PROFILE ────────────────────────────────────────────────────────────

# Fields that require moderation when edited
MODERATED_EDIT_FIELDS = {"bio", "photo", "name"}

@dp.callback_query(F.data.startswith("edit_"))
async def edit_field(call: CallbackQuery, state: FSMContext):
    field = call.data.replace("edit_", "")
    prompts = {
        "name": ("Введи новое имя:", EditProfile.name),
        "age": ("Введи новый возраст:", EditProfile.age),
        "city": ("Введи новый город:", EditProfile.city),
        "bio": ("Напиши о себе (или /skip):", EditProfile.bio),
        "photo": ("Отправь новое фото (или /skip):", EditProfile.photo),
    }
    if field == "goal":
        await call.message.edit_text("Выбери новую цель:", reply_markup=kb_goals())
        await state.set_state(EditProfile.goal)
        return
    if field == "age_filter":
        user = db.get_user(call.from_user.id)
        age_min = user.get("age_min", 18)
        age_max = user.get("age_max", 99)
        await call.message.answer(
            f"Текущий фильтр: <b>{age_min}–{age_max} лет</b>\n\n"
            f"Введи новый <b>минимальный</b> возраст:",
            parse_mode="HTML"
        )
        await state.set_state(EditProfile.age_min)
        await call.answer()
        return
    if field in prompts:
        text, st = prompts[field]
        if field in MODERATED_EDIT_FIELDS:
            text += "\n\n⚠️ Это поле требует проверки модератором."
        await call.message.answer(text)
        await state.set_state(st)
        await call.answer()

@dp.message(EditProfile.name)
async def edit_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 30:
        await message.answer("Имя от 2 до 30 символов:")
        return
    user = db.get_user(message.from_user.id)
    edit_id = db.add_pending_edit(message.from_user.id, "name", name)
    await state.clear()
    await message.answer(
        f"✅ Новое имя «<b>{name}</b>» отправлено на модерацию. Оно будет применено после проверки.",
        parse_mode="HTML", reply_markup=kb_main_menu()
    )
    await send_edit_to_admin(user, "name", name, edit_id)

@dp.message(EditProfile.age)
async def edit_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if age < 18 or age > 99: raise ValueError
    except ValueError:
        await message.answer("Введи корректный возраст (18–99):")
        return
    # Age applied immediately (no moderation needed)
    db.update_user(message.from_user.id, age=age)
    await state.clear()
    await message.answer(f"✅ Возраст обновлён: <b>{age}</b>", parse_mode="HTML", reply_markup=kb_main_menu())

@dp.message(EditProfile.city)
async def edit_city(message: Message, state: FSMContext):
    city = message.text.strip().title()
    # City applied immediately
    db.update_user(message.from_user.id, city=city)
    await state.clear()
    await message.answer(f"✅ Город обновлён: <b>{city}</b>", parse_mode="HTML", reply_markup=kb_main_menu())

@dp.callback_query(EditProfile.goal, F.data.startswith("goal_"))
async def edit_goal(call: CallbackQuery, state: FSMContext):
    goal = call.data.replace("goal_", "")
    # Goal applied immediately
    db.update_user(call.from_user.id, goal=goal)
    await state.clear()
    await call.message.edit_text(f"✅ Цель обновлена: <b>{GOALS_TEXT[goal]}</b>", parse_mode="HTML")
    await call.message.answer("Готово!", reply_markup=kb_main_menu())

@dp.message(EditProfile.bio, Command("skip"))
@dp.message(EditProfile.bio)
async def edit_bio(message: Message, state: FSMContext):
    bio = None if message.text == "/skip" else message.text.strip()[:300]
    user = db.get_user(message.from_user.id)
    edit_id = db.add_pending_edit(message.from_user.id, "bio", bio)
    await state.clear()
    await message.answer(
        "✅ Описание отправлено на модерацию. Будет применено после проверки.",
        reply_markup=kb_main_menu()
    )
    await send_edit_to_admin(user, "bio", bio, edit_id)

@dp.message(EditProfile.photo, Command("skip"))
@dp.message(EditProfile.photo, F.photo)
async def edit_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    user = db.get_user(message.from_user.id)
    edit_id = db.add_pending_edit(message.from_user.id, "photo_id", photo_id)
    await state.clear()
    await message.answer(
        "✅ Фото отправлено на модерацию. Будет применено после проверки.",
        reply_markup=kb_main_menu()
    )
    if photo_id:
        await send_edit_to_admin(user, "photo_id", photo_id, edit_id)
    else:
        db.update_user(message.from_user.id, photo_id=None)
        db.delete_pending_edit(edit_id)
        await message.answer("Фото удалено.")

@dp.message(EditProfile.photo)
async def edit_photo_wrong(message: Message):
    await message.answer("Пожалуйста, отправь фото или напиши /skip")

@dp.message(EditProfile.age_min)
async def edit_age_min(message: Message, state: FSMContext):
    try:
        age_min = int(message.text.strip())
        if age_min < 18 or age_min > 99:
            raise ValueError
    except ValueError:
        await message.answer("Введи число от 18 до 99:")
        return
    await state.update_data(age_min=age_min)
    await message.answer(
        f"Теперь введи <b>максимальный</b> возраст (не меньше {age_min}):",
        parse_mode="HTML"
    )
    await state.set_state(EditProfile.age_max)

@dp.message(EditProfile.age_max)
async def edit_age_max(message: Message, state: FSMContext):
    data = await state.get_data()
    age_min = data.get("age_min", 18)
    try:
        age_max = int(message.text.strip())
        if age_max < age_min or age_max > 99:
            raise ValueError
    except ValueError:
        await message.answer(f"Введи число от {age_min} до 99:")
        return
    db.update_user(message.from_user.id, age_min=age_min, age_max=age_max)
    await state.clear()
    await message.answer(
        f"✅ Фильтр обновлён: <b>{age_min}–{age_max} лет</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu()
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────

async def main():
    db.init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

