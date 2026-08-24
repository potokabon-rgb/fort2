import asyncio
import logging
import random
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    ChatMemberAdministrator,
    ChatMemberMember,
    ChatMemberOwner,
    FSInputFile,
    InputMediaPhoto,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
TOKEN = "8919102783:AAFlB5ICuD7WzONLHzeW5dspJKj17TT7UMg"
ADMIN_ID = 8075312868

SUPPORT_USERNAME = "@Derzywork"
REQUIRED_CHANNEL = "@FortunaPayNews"
REVIEWS_GROUP_ID = -1003589211301
REVIEWS_GROUP_USERNAME = "@FortunaPayRep"
LOG_CHANNEL_ID = -1004443604049

# Ссылка на базу данных Supabase
DATABASE_URL = "postgresql://postgres:TRKWhIlMeqpkMJBX@db.ycslyqhavhgproqrqvvs.supabase.co:5432/postgres"

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                total_deals INTEGER DEFAULT 0,
                completed_deals INTEGER DEFAULT 0,
                referrer_id BIGINT DEFAULT NULL,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount_usdt REAL,
                amount_rub REAL,
                check_link TEXT,
                phone TEXT DEFAULT '',
                bank TEXT DEFAULT '',
                fio TEXT DEFAULT '',
                status TEXT DEFAULT 'Ожидает администратора',
                admin_id BIGINT DEFAULT NULL,
                sent_rub REAL DEFAULT 0.0,
                remainder_usdt REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                action TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("INSERT INTO settings (key, value) VALUES ('rate_tier_1', '80.0') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('rate_tier_2', '90.0') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('rate_tier_3', '120.0') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('tier_limit_1', '6.0') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('tier_limit_2', '20.0') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('main_menu_photo', '') ON CONFLICT (key) DO NOTHING")
        conn.commit()
    finally:
        cursor.close()
        conn.close()

init_db()

def get_setting(key: str) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
        res = cursor.fetchone()
        return res[0] if res else ""
    finally:
        cursor.close()
        conn.close()

def update_setting(key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, value),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_rate_for_amount(amount: float) -> tuple[float, float]:
    try:
        r1 = float(get_setting("rate_tier_1"))
        r2 = float(get_setting("rate_tier_2"))
        r3 = float(get_setting("rate_tier_3"))
        lim1 = float(get_setting("tier_limit_1"))
        lim2 = float(get_setting("tier_limit_2"))
    except ValueError:
        r1, r2, r3 = 80.0, 90.0, 120.0
        lim1, lim2 = 6.0, 20.0

    if amount < lim1:
        return r1, lim1
    elif lim1 <= amount < lim2:
        return r2, lim2
    else:
        return r3, lim2

async def edit_or_reply(
    event: Message | CallbackQuery,
    text: str,
    reply_markup=None,
    state: FSMContext = None,
    photo: str = None,
):
    data = await state.get_data() if state else {}
    main_msg_id = data.get("main_msg_id")

    if isinstance(event, CallbackQuery):
        msg_obj = event.message
        try:
            if photo:
                if main_msg_id:
                    try:
                        await msg_obj.bot.delete_message(
                            chat_id=msg_obj.chat.id, message_id=main_msg_id
                        )
                    except Exception:
                        pass
                msg = await msg_obj.answer_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
                if state:
                    await state.update_data(main_msg_id=msg.message_id)
            else:
                try:
                    if msg_obj.photo:
                        await msg_obj.delete()
                        msg = await msg_obj.answer(
                            text,
                            reply_markup=reply_markup,
                            parse_mode="Markdown",
                            disable_web_page_preview=True,
                        )
                    else:
                        if main_msg_id and main_msg_id != msg_obj.message_id:
                            try:
                                await msg_obj.bot.delete_message(
                                    chat_id=msg_obj.chat.id, message_id=main_msg_id
                                )
                            except Exception:
                                pass
                        msg = await msg_obj.edit_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode="Markdown",
                            disable_web_page_preview=True,
                        )
                    if state:
                        await state.update_data(main_msg_id=msg.message_id)
                except Exception:
                    if main_msg_id:
                        try:
                            await msg_obj.bot.delete_message(
                                chat_id=msg_obj.chat.id, message_id=main_msg_id
                            )
                        except Exception:
                            pass
                    if photo:
                        msg = await msg_obj.answer_photo(
                            photo=photo,
                            caption=text,
                            reply_markup=reply_markup,
                            parse_mode="Markdown",
                        )
                    else:
                        msg = await msg_obj.answer(
                            text,
                            reply_markup=reply_markup,
                            parse_mode="Markdown",
                            disable_web_page_preview=True,
                        )
                    if state:
                        await state.update_data(main_msg_id=msg.message_id)
        except Exception as e:
            logging.error(f"Ошибка редактирования/отправки сообщения в Callback: {e}")
        await event.answer()
    else:
        if main_msg_id:
            try:
                await event.bot.delete_message(
                    chat_id=event.chat.id, message_id=main_msg_id
                )
            except Exception:
                pass

        try:
            await event.delete()
        except Exception:
            pass

        try:
            if photo:
                new_msg = await event.answer_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            else:
                new_msg = await event.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            if state:
                await state.update_data(main_msg_id=new_msg.message_id)
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения в Message: {e}")

async def send_log(user_id: int, username: str, action: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO system_logs (user_id, username, action) VALUES (%s, %s, %s)",
            (user_id, username, action),
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка записи лога в БД: {e}")
    finally:
        cursor.close()
        conn.close()

    if not LOG_CHANNEL_ID:
        return
    try:
        user_mention = f"@{username}" if username else f"ID: `{user_id}`"
        log_text = (
            f"Лог системы FortunaPay\n\nПользователь: {user_mention}\nID: `{user_id}`\nДействие: {action}"
        )
        await bot.send_message(
            chat_id=LOG_CHANNEL_ID, text=log_text, parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Ошибка отправки лога в канал: {e}")

class SellStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_balance_choice = State()
    waiting_for_receipt = State()
    waiting_for_card = State()
    waiting_for_bank = State()
    waiting_for_custom_bank = State()
    waiting_for_fio = State()

class CalcStates(StatesGroup):
    waiting_for_calc_amount = State()

class ReviewStates(StatesGroup):
    waiting_for_review_text = State()

class AdminStates(StatesGroup):
    waiting_for_rate_1 = State()
    waiting_for_rate_2 = State()
    waiting_for_rate_3 = State()
    waiting_for_limit_1 = State()
    waiting_for_limit_2 = State()
    waiting_for_payout_amount = State()
    waiting_for_broadcast = State()
    waiting_for_user_id_to_edit = State()
    waiting_for_new_balance = State()
    waiting_for_menu_photo = State()

async def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL, user_id=user_id
        )
        if isinstance(
            member, (ChatMemberOwner, ChatMemberAdministrator, ChatMemberMember)
        ):
            if member.status not in ("left", "kicked"):
                return True
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False
    return False

def sub_check_kb():
    builder = InlineKeyboardBuilder()
    if REQUIRED_CHANNEL:
        builder.button(
            text="Подписаться на канал",
            url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}",
        )
    builder.button(
        text="Проверить подписку",
        callback_data="check_sub",
    )
    builder.adjust(1)
    return builder.as_markup()

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Личный кабинет", callback_data="profile")
    builder.button(text="Продать USDT", callback_data="sell_usdt")
    builder.button(text="Калькулятор", callback_data="calculator")
    builder.button(text="Актуальные курсы", callback_data="exchange_rate")
    builder.button(text="Мои заявки", callback_data="history")
    builder.button(text="Рефералы", callback_data="referral_menu")
    builder.button(text="Отзывы", callback_data="reviews")
    builder.button(text="Поддержка", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()

def menu_button_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Главное меню", callback_data="main_menu")
    return builder.as_markup()

@router.message(Command("start"))
@router.callback_query(F.data == "main_menu")
async def cmd_start(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user = event.from_user
    user_id = user.id
    username = user.username

    referrer_id = None
    if isinstance(event, Message) and event.text:
        args = event.text.split()
        if len(args) > 1 and args[1].isdigit():
            possible_ref = int(args[1])
            if possible_ref != user_id:
                referrer_id = possible_ref

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, referrer_id FROM users WHERE user_id = %s", (user_id,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(
                "INSERT INTO users (user_id, username, referrer_id) VALUES (%s, %s, %s)",
                (user_id, username, referrer_id),
            )
        else:
            current_ref = exists[1]
            if not current_ref and referrer_id and referrer_id != user_id:
                cursor.execute(
                    "UPDATE users SET referrer_id = %s WHERE user_id = %s",
                    (referrer_id, user_id),
                )
            cursor.execute(
                "UPDATE users SET username = %s WHERE user_id = %s", (username, user_id)
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    if not await check_subscription(user_id):
        text = (
            f"🔒 **Требуется подписка**\n\nДля использования сервиса подпишитесь на официальный канал: `{REQUIRED_CHANNEL}`\n\nПосле подписки нажмите кнопку проверки ниже:"
        )
        await edit_or_reply(event, text, reply_markup=sub_check_kb(), state=state)
        return

    if isinstance(event, Message):
        await send_log(user_id, username, "Запустил бота / Главное меню")

    menu_text = (
        "👋 Добро пожаловать в FortunaPay!\n\n💱 Быстрый и надёжный обмен USDT → RUB.\n\nВыберите действие в меню ниже:"
    )

    menu_photo = get_setting("main_menu_photo")
    await edit_or_reply(
        event,
        menu_text,
        reply_markup=main_menu_kb(),
        state=state,
        photo=menu_photo if menu_photo else None,
    )

@router.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery, state: FSMContext):
    if await check_subscription(callback.from_user.id):
        menu_photo = get_setting("main_menu_photo")
        text = "✅ Подписка подтверждена!\n\nГлавное меню:"
        await edit_or_reply(
            callback,
            text,
            reply_markup=main_menu_kb(),
            state=state,
            photo=menu_photo if menu_photo else None,
        )
    else:
        await callback.answer("Вы всё еще не подписаны на канал!", show_alert=True)

@router.callback_query(F.data == "reviews")
async def reviews_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await send_log(user_id, callback.from_user.username, "Открыл отзывы")

    text = (
        "⭐ **Отзывы о сервисе FortunaPay** 💬\n\nВы можете ознакомиться с реальными отзывами наших клиентов или оставить свой собственный отзыв сразу после завершения успешного обмена! 🔥"
    )

    builder = InlineKeyboardBuilder()
    if REVIEWS_GROUP_USERNAME:
        builder.button(
            text="Почитать отзывы в канале",
            url=f"https://t.me/{REVIEWS_GROUP_USERNAME.replace('@', '')}",
        )
    builder.button(
        text="Главное меню",
        callback_data="main_menu",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)

@router.callback_query(F.data == "profile")
async def user_profile(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    username = callback.from_user.username
    await send_log(user_id, username, "Открыл профиль")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT balance, total_deals, completed_deals, joined_date FROM users WHERE user_id = %s",
            (user_id,),
        )
        res = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    balance, total, completed, joined = (
        res if res else (0.0, 0, 0, "Неизвестно")
    )

    profile_text = (
        f"👤 **Личный кабинет** ✨\n\n🆔 ID: `{user_id}`\n💬 Юзернейм: @{username if username else 'отсутствует'}\n📅 Регистрация: `{joined}`\n\n📊 **Статистика сделок:** 📈\n🪙 Баланс аккаунта: `{balance:.2f} USDT` 💎\n📁 Всего заявок: `{total}` (Успешно: `{completed}`) 🔥"
    )

    await edit_or_reply(
        callback, profile_text, reply_markup=menu_button_kb(), state=state
    )

@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = %s", (user_id,))
        ref_count = cursor.fetchone()[0]
    finally:
        cursor.close()
        conn.close()

    text = (
        f"🎁 **Реферальная система (3%)** 💎\n\nПриглашайте друзей и получайте **3%** от суммы их успешных обменов прямо на ваш баланс! 🚀\n\n🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n👥 Приглашено пользователей: `{ref_count}` 🔥"
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)

@router.callback_query(F.data == "calculator")
async def calculator_start(callback: CallbackQuery, state: FSMContext):
    await send_log(
        callback.from_user.id, callback.from_user.username, "Открыл калькулятор"
    )
    r1 = get_setting("rate_tier_1")
    r2 = get_setting("rate_tier_2")
    r3 = get_setting("rate_tier_3")
    lim1 = get_setting("tier_limit_1")
    lim2 = get_setting("tier_limit_2")

    text = (
        f"🧮 **Калькулятор USDT ➔ RUB** 📊\n\nДействующие тарифные ставки:\n🔹 • До {lim1} USDT ➔ `{r1} ₽`\n🔹 • От {lim1} до {lim2} USDT ➔ `{r2} ₽`\n🔹 • От {lim2} USDT ➔ `{r3} ₽`\n\n💬 Отправляйте числа сообщением — сумма будет пересчитываться автоматически:"
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(CalcStates.waiting_for_calc_amount)

@router.message(CalcStates.waiting_for_calc_amount)
async def calculator_process(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        text = "Некорректная сумма.\n\nВведите число (например, `5` или `50.5`):"
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    rate, _ = get_rate_for_amount(amount)
    total_rub = round(amount * rate, 2)

    text = (
        f"📈 **Результат расчета:** 🪙\n\nСумма к обмену: `{amount} USDT`\nПримененный курс: `{rate} ₽` / USDT\nВы получите: `{total_rub} ₽` 🔥\n\n*Можете отправить другое число для мгновенного пересчета:*"
    )

    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)

@router.callback_query(F.data == "sell_usdt")
async def sell_usdt_start(callback: CallbackQuery, state: FSMContext):
    await send_log(
        callback.from_user.id,
        callback.from_user.username,
        "Начал создание заявки на продажу",
    )

    r1 = get_setting("rate_tier_1")
    r2 = get_setting("rate_tier_2")
    r3 = get_setting("rate_tier_3")
    lim1 = get_setting("tier_limit_1")
    lim2 = get_setting("tier_limit_2")

    text = (
        f"💎 **Создание заявки на обмен** 🚀\n\n📊 Действующие курсы:\n🔹 • До {lim1}$ ➔ `{r1} ₽`\n🔹 • {lim1}-{lim2}$ ➔ `{r2} ₽`\n🔹 • От {lim2}$ ➔ `{r3} ₽`\n\n🪙 Отправьте сообщением сумму USDT, которую хотите обменять:"
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_amount)

@router.message(SellStates.waiting_for_amount)
async def process_sell_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        text = "Ошибка ввода. Введите корректное число USDT (например, `10` или `25.5`):"
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    user_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        res = cursor.fetchone()
        user_balance = res[0] if res else 0.0
    finally:
        cursor.close()
        conn.close()

    rate, _ = get_rate_for_amount(amount)
    total_rub = round(amount * rate, 2)

    await state.update_data(
        amount_usdt=amount, amount_rub=total_rub, user_balance=user_balance
    )

    if user_balance > 0:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"Списать с баланса ({min(user_balance, amount):.2f} USDT)",
            callback_data="use_balance_yes",
        )
        builder.button(
            text="Оплатить полностью через чек",
            callback_data="use_balance_no",
        )
        builder.button(
            text="Главное меню",
            callback_data="main_menu",
        )
        builder.adjust(1)

        text = (
            f"🪙 Обнаружен внутренний баланс: `{user_balance:.2f} USDT`\n\nЖелаете ли вы использовать средства с баланса для частичной или полной оплаты заявки на `{amount} USDT`?"
        )
        await edit_or_reply(
            message, text, reply_markup=builder.as_markup(), state=state
        )
        await state.set_state(SellStates.waiting_for_balance_choice)
    else:
        text = (
            f"Заявка: {amount} USDT (`{total_rub} ₽`)\nКурс: `{rate} ₽` / USDT\n\nШаг 1 из 4: Отправьте ссылку на чек из @CryptoBot\n*(Пример: `https://t.me/CryptoBot?start=...`)*:"
        )
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        await state.set_state(SellStates.waiting_for_receipt)

@router.callback_query(
    F.data.in_({"use_balance_yes", "use_balance_no"}),
    StateFilter(SellStates.waiting_for_balance_choice),
)
async def process_balance_choice(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount_usdt = data.get("amount_usdt")
    amount_rub = data.get("amount_rub")
    user_balance = data.get("user_balance")
    user_id = callback.from_user.id

    used_from_balance = 0.0

    if callback.data == "use_balance_yes":
        if user_balance >= amount_usdt:
            used_from_balance = amount_usdt
        else:
            used_from_balance = user_balance

    await state.update_data(used_from_balance=used_from_balance)

    if callback.data == "use_balance_yes" and user_balance >= amount_usdt:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id = %s",
                (amount_usdt, user_id),
            )
            cursor.execute(
                """
                INSERT INTO orders (user_id, amount_usdt, amount_rub, check_link, status)
                VALUES (%s, %s, %s, 'Оплачено с баланса', 'Ожидает реквизиты')
                RETURNING id
                """,
                (user_id, amount_usdt, amount_rub),
            )
            order_id = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE users SET total_deals = total_deals + 1 WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        await state.update_data(order_id=order_id, check_link="Оплачено с баланса")

        text = "Оплата с баланса успешна!\n\nШаг 2 из 4: Укажите **номер карты** или **номер телефона**:"
        await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
        await state.set_state(SellStates.waiting_for_card)
    else:
        link_instruction = (
            f"С баланса списано `{used_from_balance:.2f} USDT`. Остаток нужно доплатить через чек."
            if used_from_balance > 0
            else "Отправьте ссылку на чек из `@CryptoBot`:"
        )
        text = f"Заявка: {amount_usdt} USDT (`{amount_rub} ₽`)\n\n{link_instruction}"
        await edit_or_reply(
            message=callback, text=text, reply_markup=menu_button_kb(), state=state
        )
        await state.set_state(SellStates.waiting_for_receipt)

@router.message(SellStates.waiting_for_receipt)
async def process_sell_receipt_link(message: Message, state: FSMContext):
    check_link = message.text.strip()

    crypto_bot_pattern = r"^https?://t\.me/(CryptoBot|send\b|cryptobot\b).*$"
    if not re.match(crypto_bot_pattern, check_link, re.IGNORECASE) and "t.me/" not in check_link.lower():
        text = (
            "❌ **Некорректная ссылка на чек.**\n\nПожалуйста, отправьте действительную ссылку из официального бота `@CryptoBot`\n*(Пример: `https://t.me/CryptoBot?start=...`)*:"
        )
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    data = await state.get_data()
    amount_usdt = data.get("amount_usdt")
    amount_rub = data.get("amount_rub")
    used_from_balance = data.get("used_from_balance", 0.0)
    user_id = message.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if used_from_balance > 0:
            cursor.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id = %s",
                (used_from_balance, user_id),
            )

        cursor.execute(
            """
            INSERT INTO orders (user_id, amount_usdt, amount_rub, check_link, status)
            VALUES (%s, %s, %s, %s, 'Ожидает реквизиты')
            RETURNING id
            """,
            (user_id, amount_usdt, amount_rub, check_link),
        )
        order_id = cursor.fetchone()[0]
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await state.update_data(order_id=order_id, check_link=check_link)

    text = "✅ **Ссылка принята!**\n\nШаг 2 из 4: Укажите **номер карты** или **номер телефона**:"
    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_card)

@router.message(SellStates.waiting_for_card)
async def process_sell_card(message: Message, state: FSMContext):
    card_data = message.text.strip()
    if len(card_data) < 5:
        text = "Слишком короткий номер. Введите корректный номер карты или телефона:"
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    await state.update_data(temp_card=card_data)

    builder = InlineKeyboardBuilder()
    builder.button(text="Т-Банк", callback_data="bank_tinkoff")
    builder.button(text="Сбербанк", callback_data="bank_sber")
    builder.button(text="Другой банк", callback_data="bank_other")
    builder.adjust(1)

    text = "Шаг 3 из 4: Выберите банк получателя:"
    await edit_or_reply(message, text, reply_markup=builder.as_markup(), state=state)
    await state.set_state(SellStates.waiting_for_bank)

@router.callback_query(
    F.data.startswith("bank_"), StateFilter(SellStates.waiting_for_bank)
)
async def process_sell_bank_choice(callback: CallbackQuery, state: FSMContext):
    bank_map = {
        "bank_tinkoff": "Т-Банк",
        "bank_sber": "Сбербанк",
    }

    if callback.data == "bank_other":
        text = "Введите название вашего банка:"
        await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
        await state.set_state(SellStates.waiting_for_custom_bank)
        return

    selected_bank = bank_map.get(callback.data, "Т-Банк")
    await state.update_data(temp_bank=selected_bank)

    text = (
        f"Банк выбран: **{selected_bank}**\n\nШаг 4 из 4: Введите **ФИО получателя** полностью (например, `Иванов Иван Иванович`):"
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_fio)

@router.message(SellStates.waiting_for_custom_bank)
async def process_custom_bank(message: Message, state: FSMContext):
    custom_bank = message.text.strip()
    if len(custom_bank) < 2:
        text = "Слишком короткое название. Введите корректное название банка:"
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    await state.update_data(temp_bank=custom_bank)

    text = (
        f"Банк выбран: **{custom_bank}**\n\nШаг 4 из 4: Введите **ФИО получателя** полностью (например, `Иванов Иван Иванович`):"
    )
    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_fio)

@router.message(SellStates.waiting_for_fio)
async def process_sell_fio(message: Message, state: FSMContext):
    fio = message.text.strip()
    if len(fio.split()) < 2:
        text = "Пожалуйста, введите Фамилию и Имя полностью:"
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    phone = data.get("temp_card")
    bank = data.get("temp_bank")
    amount_usdt = data.get("amount_usdt")
    amount_rub = data.get("amount_rub")
    check_link = data.get("check_link")
    used_from_balance = data.get("used_from_balance", 0.0)

    user_id = message.from_user.id
    username = message.from_user.username

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE orders
            SET phone = %s,
                bank = %s,
                fio = %s,
                status = 'Ожидает администратора'
            WHERE id = %s
            """,
            (phone, bank, fio, order_id),
        )

        cursor.execute(
            "UPDATE users SET total_deals = total_deals + 1 WHERE user_id = %s",
            (user_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await send_log(
        user_id, username, f"Создал заявку #{order_id} на сумму {amount_usdt} USDT"
    )

    balance_note = (
        f"\nСписано с баланса: `{used_from_balance:.2f} USDT`"
        if used_from_balance > 0
        else ""
    )
    raw_req = f"{phone}, {bank}, {fio}"
    success_text = (
        f"Заявка #{order_id} полностью сформирована!\n\nСумма: `{amount_usdt} USDT` (`{amount_rub} ₽`){balance_note}\nРеквизиты: `{raw_req}`\n\nСтатус: **Ожидает обработку администратором...**"
    )
    await edit_or_reply(message, success_text, reply_markup=main_menu_kb(), state=state)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Взять заявку",
        callback_data=f"take_order_{order_id}",
    )

    admin_text = (
        f"🔔 **НОВАЯ ЗАЯВКА #{order_id} ГОТОВА К ОБРАБОТКЕ!**\n\nПользователь: @{username} (`{user_id}`)\nСумма: `{amount_usdt} USDT` (`{amount_rub} ₽`){balance_note}\nРеквизиты: `{raw_req}`\nЧек: {check_link}"
    )

    try:
        await message.bot.send_message(
            chat_id=int(ADMIN_ID),
            text=admin_text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление админу: {e}")

    await state.clear()

@router.callback_query(F.data.startswith("take_order_"))
async def take_order_handler(callback: CallbackQuery):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Вы не администратор!", show_alert=True)
        return

    order_id = int(callback.data.split("_")[-1])
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status, user_id FROM orders WHERE id = %s", (order_id,))
        res = cursor.fetchone()

        if not res:
            await callback.answer("Заявка не найдена в базе.", show_alert=True)
            return

        status, client_id = res
        if status not in ("Ожидает администратора", "Ожидает реквизиты"):
            await callback.answer(
                f"Заявка уже обработана или находится в статусе: {status}",
                show_alert=True,
            )
            return

        cursor.execute(
            "UPDATE orders SET status = 'В работе', admin_id = %s WHERE id = %s",
            (callback.from_user.id, order_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Ввести отправленную сумму",
        callback_data=f"pay_order_{order_id}",
    )

    try:
        await callback.message.edit_text(
            text=(
                callback.message.text
                + f"\n\nВ работе у: @{callback.from_user.username}"
            ),
            reply_markup=builder.as_markup(),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await callback.answer(f"Заявка #{order_id} взята в работу!")

    try:
        await bot.send_message(
            chat_id=client_id,
            text=f"Ваша заявка #{order_id} взята в обработку администратором! Идет проверка чека и выплата.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Не удалось уведомить клиента: {e}")

@router.callback_query(F.data.startswith("pay_order_"))
async def pay_order_handler(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Вы не администратор!", show_alert=True)
        return

    order_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    await state.set_state(AdminStates.waiting_for_payout_amount)
    await state.update_data(
        order_id=order_id, main_msg_id=data.get("main_msg_id")
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отмена",
        callback_data="adm_menu",
    )

    await edit_or_reply(
        callback,
        f"Введите фактически переведенную сумму в рублях (`RUB`) для заявки **#{order_id}**:",
        reply_markup=builder.as_markup(),
        state=state,
    )

@router.message(AdminStates.waiting_for_payout_amount)
async def process_admin_payout_amount(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return

    try:
        sent_rub = float(message.text.strip().replace(",", "."))
        if sent_rub < 0:
            raise ValueError
    except ValueError:
        await edit_or_reply(
            message,
            "Ошибка ввода. Введите корректную сумму числом (например, `1500`):",
            state=state,
        )
        return

    data = await state.get_data()
    order_id = data.get("order_id")

    if not order_id:
        await edit_or_reply(
            message,
            "Сессия обработки заказа не найдена.",
            reply_markup=menu_button_kb(),
            state=state,
        )
        await state.clear()
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT user_id, amount_rub, amount_usdt FROM orders WHERE id = %s",
            (order_id,),
        )
        res = cursor.fetchone()

        if not res:
            await edit_or_reply(
                message,
                "Заявка не найдена.",
                reply_markup=menu_button_kb(),
                state=state,
            )
            await state.clear()
            return

        client_id, expected_rub, amount_usdt = res

        if sent_rub < expected_rub:
            remainder_rub = round(expected_rub - sent_rub, 2)
            rate, _ = get_rate_for_amount(amount_usdt)
            remainder_usdt = round(remainder_rub / rate, 2)

            cursor.execute(
                "UPDATE orders SET sent_rub = %s, remainder_usdt = %s, status = 'Ожидает решения по остатку' WHERE id = %s",
                (sent_rub, remainder_usdt, order_id),
            )
            conn.commit()

            builder = InlineKeyboardBuilder()
            builder.button(
                text="Зачислить остаток на баланс ($)",
                callback_data=f"usr_rem_balance_{order_id}",
            )
            builder.button(
                text="Оставить на чай",
                callback_data=f"usr_rem_tip_{order_id}",
            )
            builder.adjust(1)

            user_text = (
                f"Выплата по заявке #{order_id} частичная!\n\nПереведено: `{sent_rub} ₽` из `{expected_rub} ₽`\nНедоплата составила: `{remainder_rub} ₽` (≈ `{remainder_usdt} USDT`)\n\nУкажите, как поступить с остатком средств:"
            )

            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=user_text,
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown",
                )
                await edit_or_reply(
                    message,
                    f"Перевод зафиксирован частично (`{sent_rub} ₽`). Запрос решений отправлен клиенту #{client_id}.",
                    state=state,
                )
            except Exception as e:
                logging.error(f"Ошибка уведомления клиента: {e}")
        else:
            cursor.execute(
                "UPDATE orders SET sent_rub = %s, status = 'Ожидает подтверждения' WHERE id = %s",
                (sent_rub, order_id),
            )
            conn.commit()

            await finalize_payout(bot, client_id, sent_rub, order_id)
            await edit_or_reply(
                message,
                f"Выплата по заявке #{order_id} на сумму {sent_rub} ₽ проведена.",
                state=state,
            )
    finally:
        cursor.close()
        conn.close()

    await state.clear()

@router.callback_query(
    F.data.startswith("usr_rem_balance_") | F.data.startswith("usr_rem_tip_")
)
async def process_user_remainder_choice(
    callback: CallbackQuery, state: FSMContext
):
    action = "balance" if "usr_rem_balance_" in callback.data else "tip"
    order_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT remainder_usdt, sent_rub FROM orders WHERE id = %s AND user_id = %s",
            (order_id, user_id),
        )
        res = cursor.fetchone()

        if not res:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        remainder_usdt, sent_rub = res

        if action == "balance":
            cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                (remainder_usdt, user_id),
            )
            choice_text = (
                f"Остаток `{remainder_usdt:.2f} USDT` успешно зачислен на ваш внутренний баланс!"
            )
        else:
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES ('total_tips_usdt', '0') ON CONFLICT (key) DO NOTHING"
            )
            cursor.execute(
                "UPDATE settings SET value = (value::REAL + %s)::TEXT WHERE key = 'total_tips_usdt'",
                (remainder_usdt,),
            )
            choice_text = "Большое спасибо! Остаток передан в качестве чаевых."

        cursor.execute(
            "UPDATE orders SET status = 'Ожидает подтверждения' WHERE id = %s",
            (order_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await edit_or_reply(
        callback, f"Ваш выбор принят.\n\n{choice_text}", state=state
    )
    await finalize_payout(
        bot, user_id, sent_rub, order_id, extra_text=choice_text
    )

async def finalize_payout(
    bot_instance: Bot,
    client_id: int,
    sent_rub: float,
    order_id: int,
    extra_text: str = "",
):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Деньги пришли",
        callback_data=f"confirm_yes_{order_id}",
    )
    builder.button(
        text="Деньги не пришли",
        callback_data=f"confirm_no_{order_id}",
    )
    builder.adjust(2)

    extra_block = f"{extra_text}\n" if extra_text else ""
    text = (
        f"Выплата по заявке #{order_id} отправлена!\n\nСумма перевода:`{sent_rub}` ₽\n{extra_block}\nПожалуйста, проверьте баланс карты и подтвердите получение:"
    )

    try:
        await bot_instance.send_message(
            chat_id=client_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Не удалось отправить статус клиенту: {e}")

@router.callback_query(F.data.startswith("confirm_yes_"))
async def confirm_yes_handler(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT status, amount_usdt FROM orders WHERE id = %s AND user_id = %s",
            (order_id, user_id),
        )
        res = cursor.fetchone()

        if not res:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        status, amount_usdt = res
        if status == "Завершено":
            await callback.answer("Сделка уже подтверждена ранее.", show_alert=True)
            return

        cursor.execute(
            "UPDATE orders SET status = 'Завершено' WHERE id = %s", (order_id,)
        )
        cursor.execute(
            "UPDATE users SET completed_deals = completed_deals + 1 WHERE user_id = %s",
            (user_id,),
        )

        cursor.execute(
            "SELECT referrer_id FROM users WHERE user_id = %s", (user_id,)
        )
        ref_res = cursor.fetchone()
        if ref_res and ref_res[0]:
            referrer_id = ref_res[0]
            bonus = round(amount_usdt * 0.03, 4)
            cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                (bonus, referrer_id),
            )
            try:
                await bot.send_message(
                    chat_id=referrer_id,
                    text=f"Реферальный бонус!\nПользователь по вашей ссылке успешно завершил обмен. Вам начислено `{bonus} USDT` (3%).",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await send_log(
        user_id, callback.from_user.username, f"Успешно закрыл сделку #{order_id}"
    )

    data = await state.get_data()
    await state.set_state(ReviewStates.waiting_for_review_text)
    await state.update_data(order_id=order_id, main_msg_id=data.get("main_msg_id"))

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Пропустить отзыв",
        callback_data="skip_review",
    )

    await edit_or_reply(
        callback,
        f"Сделка #{order_id} успешно завершена!\n\nНапишите короткий отзыв о работе сервиса FortunaPay ниже:",
        reply_markup=builder.as_markup(),
        state=state,
    )

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=f"Пользователь подтвердил получение средств по заявке #{order_id}. Сделка закрыта!",
            parse_mode="Markdown",
        )
    except Exception:
        pass

@router.callback_query(F.data == "skip_review")
async def skip_review_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    menu_photo = get_setting("main_menu_photo")
    await edit_or_reply(
        callback,
        "Спасибо за обмен! Будем рады сотрудничать снова.",
        reply_markup=main_menu_kb(),
        state=state,
        photo=menu_photo if menu_photo else None,
    )

@router.message(ReviewStates.waiting_for_review_text)
async def process_user_review(message: Message, state: FSMContext):
    review_text = message.text.strip()
    user = message.from_user
    user_id = user.id
    username = user.username
    user_mention = f"@{username}" if username else f"ID: `{user_id}`"
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")

    formatted_review = (
        f"Новый отзыв о FortunaPay\n\nОт: {user_mention}\nДата: `{current_date}`\n\nКомментарий:\n{review_text}"
    )

    if REVIEWS_GROUP_ID:
        try:
            await bot.send_message(
                chat_id=REVIEWS_GROUP_ID,
                text=formatted_review,
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить отзыв в группу: {e}")

    await send_log(user_id, username, "Оставил отзыв")
    await state.clear()

    menu_photo = get_setting("main_menu_photo")
    await edit_or_reply(
        message,
        "Спасибо за ваш отзыв! Он передан в публичный канал отзывов.",
        reply_markup=main_menu_kb(),
        state=state,
        photo=menu_photo if menu_photo else None,
    )

@router.callback_query(F.data.startswith("confirm_no_"))
async def confirm_no_handler(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    await send_log(
        user_id,
        callback.from_user.username,
        f"Сообщил о проблеме с выплатой по заявке #{order_id}",
    )
    random_code = random.randint(1000, 9999)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Написать поддержке",
        url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}",
    )
    builder.button(
        text="Главное меню",
        callback_data="main_menu",
    )
    builder.adjust(1)

    instruction_text = (
        f"Фиксация проблемы по заявке #{order_id}\n\nДля решения диспута запишите видео экрана:\n\n1. Откройте мобильное приложение банка\n2. Покажите привязанный номер телефона\n3. Пролистайте историю операций за сегодня\n4. Откройте чек любой последней операции\n5. Напишите код `{random_code}` в любом поле ввода\n\nОтправьте запись администратору поддержки."
    )

    await edit_or_reply(
        callback, instruction_text, reply_markup=builder.as_markup(), state=state
    )

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=f"ВНИМАНИЕ! Диспут по заявке #{order_id}. Клиент указал, что деньги не пришли (Код проверки: {random_code})",
            parse_mode="Markdown",
        )
    except Exception:
        pass

@router.callback_query(F.data == "exchange_rate")
async def exchange_rate_handler(callback: CallbackQuery, state: FSMContext):
    await send_log(
        callback.from_user.id, callback.from_user.username, "Посмотрел курс"
    )
    r1 = get_setting("rate_tier_1")
    r2 = get_setting("rate_tier_2")
    r3 = get_setting("rate_tier_3")
    lim1 = get_setting("tier_limit_1")
    lim2 = get_setting("tier_limit_2")

    text = (
        f"📊 **Актуальные курсы обмена** 🪙\n\n🔹 • До {lim1} USDT ➔ `{r1} ₽` за 1 USDT\n🔹 • От {lim1} до {lim2} USDT ➔ `{r2} ₽` за 1 USDT\n🔹 • От {lim2} USDT ➔ `{r3} ₽` за 1 USDT\n\nℹ️ Расчет курса пересчитывается автоматически."
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)

@router.callback_query(F.data == "history")
async def history_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await send_log(user_id, callback.from_user.username, "Просмотр истории")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status = 'Завершено' THEN 1 ELSE 0 END) FROM orders WHERE user_id = %s",
            (user_id,),
        )
        total_q, completed_q = cursor.fetchone()
        total_q = total_q or 0
        completed_q = completed_q or 0

        cursor.execute(
            "SELECT id, amount_usdt, amount_rub, status FROM orders WHERE user_id = %s ORDER BY id DESC LIMIT 5",
            (user_id,),
        )
        orders = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    text = (
        f"📁 **История ваших операций** 📊\n\nВсего заявок: `{total_q}` | Завершено: `{completed_q}`\n\nПоследние действия:"
    )

    builder = InlineKeyboardBuilder()
    if orders:
        for o_id, a_usdt, a_rub, status in orders:
            builder.button(
                text=f"#{o_id} | {a_usdt} USDT ({status})",
                callback_data=f"view_order_{o_id}",
            )

    builder.button(
        text="Главное меню",
        callback_data="main_menu",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)

@router.callback_query(F.data.startswith("view_order_"))
async def view_order_details(callback: CallbackQuery, state: FSMContext):
    o_id = int(callback.data.split("_")[-1])
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT amount_usdt, amount_rub, status, check_link, phone, bank, fio, created_at FROM orders WHERE id = %s AND user_id = %s",
            (o_id, callback.from_user.id),
        )
        res = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not res:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    usdt, rub, status, link, phone, bank, fio, created = res
    text = (
        f"Детали заявки #{o_id}\n\nСумма: `{usdt} USDT`\nОжидается к выплате: `{rub} ₽`\nТелефон/Карта: `{phone}`\nБанк: `{bank}`\nФИО: `{fio}`\nТекущий статус: `{status}`\nЧек: {link}\nВремя создания: `{created}`"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="К истории",
        callback_data="history",
    )
    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)

@router.message(Command("staff"))
async def admin_panel_command(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        await message.answer("Недостаточно прав!")
        return
    await state.clear()
    await show_admin_menu(message, state)

async def show_admin_menu(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if user_id != int(ADMIN_ID):
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('Ожидает администратора', 'Ожидает реквизиты')"
        )
        pending_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('В работе', 'Ожидает решения по остатку', 'Ожидает подтверждения')"
        )
        in_progress_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'Завершено'")
        completed_count = cursor.fetchone()[0]

        cursor.execute("SELECT value FROM settings WHERE key = 'total_tips_usdt'")
        tip_res = cursor.fetchone()
        total_tips = float(tip_res[0]) if tip_res else 0.0
    finally:
        cursor.close()
        conn.close()

    r1 = get_setting("rate_tier_1")
    r2 = get_setting("rate_tier_2")
    r3 = get_setting("rate_tier_3")
    lim1 = get_setting("tier_limit_1")
    lim2 = get_setting("tier_limit_2")

    text = (
        f"Панель управления сервисом FortunaPay\n\nВсего пользователей: `{users_count}`\nНовые заявки: `{pending_count}`\nАктивные заявки в работе: `{in_progress_count}`\nУспешно завершено сделок: `{completed_count}`\n💰 Всего оставили на чай: `{total_tips:.2f} USDT`\n\nТекущие курсы и лимиты:\n• До {lim1}$ ➔ `{r1} ₽`\n• {lim1}-{lim2}$ ➔ `{r2} ₽`\n• От {lim2}$ ➔ `{r3} ₽`"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=f"Ожидают ({pending_count})", callback_data="adm_pending_orders")
    builder.button(text=f"В работе ({in_progress_count})", callback_data="adm_in_progress_orders")
    builder.button(text="Завершенные сделки", callback_data="adm_completed_orders")
    builder.button(text="Изменить баланс юзера", callback_data="adm_edit_balance_start")
    builder.button(text="Изменить курсы/лимиты", callback_data="adm_rates_menu")
    builder.button(text="🖼 Изменить фото меню", callback_data="adm_set_menu_photo")
    builder.button(text="Рассылка", callback_data="adm_broadcast")
    builder.button(text="Выгрузить юзеров (TXT)", callback_data="adm_export_users")
    builder.button(text="Выгрузить логи (TXT)", callback_data="adm_export_system_logs")
    builder.button(text="Выход в меню", callback_data="main_menu")
    builder.adjust(2, 1, 1, 2, 2, 2, 1)

    await edit_or_reply(event, text, reply_markup=builder.as_markup(), state=state)

@router.callback_query(F.data == "adm_menu")
async def adm_menu_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    await show_admin_menu(callback, state)

@router.callback_query(F.data == "adm_set_menu_photo")
async def adm_set_menu_photo_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить текущее фото", callback_data="adm_clear_menu_photo")
    builder.button(text="Отмена", callback_data="adm_menu")
    builder.adjust(1)
    await edit_or_reply(
        callback,
        "Отправьте картинку (фотографию), которая будет отображаться в главном меню бота:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_menu_photo)

@router.callback_query(F.data == "adm_clear_menu_photo")
async def adm_clear_menu_photo(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    update_setting("main_menu_photo", "")
    await state.clear()
    await callback.answer("Фотография главного меню удалена!", show_alert=True)
    await show_admin_menu(callback, state)

@router.message(AdminStates.waiting_for_menu_photo, F.photo)
async def adm_save_menu_photo(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    photo_id = message.photo[-1].file_id
    update_setting("main_menu_photo", photo_id)
    await state.clear()
    await message.answer("Фотография главного меню успешно обновлена!")
    await show_admin_menu(message, state)

@router.message(AdminStates.waiting_for_menu_photo)
async def adm_wrong_menu_photo(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    await message.answer(
        "Пожалуйста, отправьте именно **изображение (фото)** или нажмите кнопку отмены:"
    )

@router.callback_query(F.data == "adm_edit_balance_start")
async def adm_edit_balance_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_menu")
    await edit_or_reply(
        callback,
        "Введите **Telegram ID** пользователя, баланс которого хотите изменить:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_user_id_to_edit)

@router.message(AdminStates.waiting_for_user_id_to_edit)
async def adm_edit_balance_get_user(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Некорректный ID. Введите числовой Telegram ID:")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT balance, username FROM users WHERE user_id = %s", (target_id,)
        )
        res = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not res:
        await message.answer(
            f"Пользователь с ID `{target_id}` не найден в базе данных.",
            parse_mode="Markdown",
        )
        return

    current_balance, uname = res
    await state.update_data(target_id=target_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_menu")

    await edit_or_reply(
        message,
        f"Пользователь: @{uname or 'отсутствует'} (`{target_id}`)\nТекущий баланс: `{current_balance:.2f} USDT`\n\nВведите новое значение баланса (число, например `15.5` или `0`):",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_new_balance)

@router.message(AdminStates.waiting_for_new_balance)
async def adm_edit_balance_save(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        new_balance = float(message.text.strip().replace(",", "."))
        if new_balance < 0:
            raise ValueError
    except ValueError:
        await message.answer("Некорректная сумма. Введите положительное число:")
        return

    data = await state.get_data()
    target_id = data.get("target_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET balance = %s WHERE user_id = %s", (new_balance, target_id)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await state.clear()
    await message.answer(
        f"Баланс пользователя `{target_id}` успешно изменен на `{new_balance:.2f} USDT`!",
        parse_mode="Markdown",
    )

    try:
        await bot.send_message(
            chat_id=target_id,
            text=f"Администратор обновил ваш баланс. Текущий баланс: `{new_balance:.2f} USDT`",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await show_admin_menu(message, state)

@router.callback_query(F.data == "adm_rates_menu")
async def adm_rates_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="Курс (1)", callback_data="adm_set_rate_1")
    builder.button(text="Курс (2)", callback_data="adm_set_rate_2")
    builder.button(text="Курс (3)", callback_data="adm_set_rate_3")
    builder.button(text="Лимит 1", callback_data="adm_set_limit_1")
    builder.button(text="Лимит 2", callback_data="adm_set_limit_2")
    builder.button(text="Назад", callback_data="adm_menu")
    builder.adjust(3, 2, 1)
    await edit_or_reply(
        callback,
        "Управление курсами и диапазонами:",
        reply_markup=builder.as_markup(),
        state=state,
    )

@router.callback_query(F.data == "adm_pending_orders")
async def adm_pending_orders(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, user_id, amount_usdt, amount_rub, phone, bank, fio, status, check_link
            FROM orders
            WHERE status IN ('Ожидает администратора', 'Ожидает реквизиты')
            ORDER BY id ASC
        """)
        orders = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not orders:
        await callback.answer("Нет нераспределенных заявок.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    text = "Необработанные заявки:\n\n"
    for o_id, u_id, usdt, rub, phone, bank, fio, status, check_link in orders:
        req_info = (
            f"📞 `{phone}` | 🏦 `{bank}` | 👤 `{fio}`"
            if phone
            else "*Реквизиты еще не введены*"
        )
        text += (
            f"🆔 **#{o_id}** [{status}] | `{usdt} USDT` (`{rub} ₽`)\n🔗 Чек: {check_link}\n{req_info}\n\n"
        )
        builder.button(
            text=f"Взять #{o_id}",
            callback_data=f"take_order_{o_id}",
        )

    builder.button(
        text="Панель управления",
        callback_data="adm_menu",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)

@router.callback_query(F.data == "adm_in_progress_orders")
async def adm_in_progress_orders(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, user_id, amount_usdt, amount_rub, phone, bank, fio, status
            FROM orders
            WHERE status IN ('В работе', 'Ожидает решения по остатку', 'Ожидает подтверждения')
            ORDER BY id DESC
        """)
        orders = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not orders:
        await callback.answer("Нет активных процессов.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    text = "Заявки в обработке:\n\n"
    for o_id, u_id, usdt, rub, phone, bank, fio, status in orders:
        text += (
            f"🆔 **#{o_id}** [{status}] | `{usdt} USDT` (`{rub} ₽`)\n📞 `{phone}` | 🏦 `{bank}` | 👤 `{fio}`\n\n"
        )
        builder.button(
            text=f"Перевод по #{o_id}",
            callback_data=f"pay_order_{o_id}",
        )

    builder.button(
        text="Панель управления",
        callback_data="adm_menu",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)

@router.callback_query(F.data == "adm_completed_orders")
async def adm_completed_orders(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, user_id, amount_usdt, amount_rub, sent_rub
            FROM orders
            WHERE status = 'Завершено'
            ORDER BY id DESC LIMIT 15
        """)
        orders = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not orders:
        await callback.answer("Завершенных сделок пока нет.", show_alert=True)
        return

    text = "История последних выполненных сделок:\n\n"
    for o_id, u_id, usdt, rub, sent_rub in orders:
        text += f"🆔 **#{o_id}** | ID Клиента: `{u_id}` | `{usdt} USDT` ➔ `{sent_rub or rub} ₽`\n"

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Панель управления",
        callback_data="adm_menu",
    )

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_menu")
    await edit_or_reply(
        callback,
        "Отправьте текст для рассылки всем пользователям:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_broadcast)

@router.message(AdminStates.waiting_for_broadcast)
async def adm_broadcast_process(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    text = message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    success, failed = 0, 0
    await message.answer("Рассылка запущена...")
    for (uid,) in users:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await message.answer(
        f"Рассылка завершена!\nУспешно: `{success}`\nНе удалось: `{failed}`"
    )
    await state.clear()
    await show_admin_menu(message, state)

@router.callback_query(F.data == "adm_set_rate_1")
async def adm_set_rate_1_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_rates_menu")
    await edit_or_reply(
        callback,
        "Введите новый курс для Tier 1:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_rate_1)

@router.message(AdminStates.waiting_for_rate_1)
async def adm_save_rate_1(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        update_setting("rate_tier_1", str(val))
        await state.clear()
        await show_admin_menu(message, state)
    except ValueError:
        await edit_or_reply(message, "Введите корректное число:", state=state)

@router.callback_query(F.data == "adm_set_rate_2")
async def adm_set_rate_2_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_rates_menu")
    await edit_or_reply(
        callback,
        "Введите новый курс для Tier 2:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_rate_2)

@router.message(AdminStates.waiting_for_rate_2)
async def adm_save_rate_2(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        update_setting("rate_tier_2", str(val))
        await state.clear()
        await show_admin_menu(message, state)
    except ValueError:
        await edit_or_reply(message, "Введите корректное число:", state=state)

@router.callback_query(F.data == "adm_set_rate_3")
async def adm_set_rate_3_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_rates_menu")
    await edit_or_reply(
        callback,
        "Введите новый курс для Tier 3:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_rate_3)

@router.message(AdminStates.waiting_for_rate_3)
async def adm_save_rate_3(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        update_setting("rate_tier_3", str(val))
        await state.clear()
        await show_admin_menu(message, state)
    except ValueError:
        await edit_or_reply(message, "Введите корректное число:", state=state)

@router.callback_query(F.data == "adm_set_limit_1")
async def adm_set_limit_1_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_rates_menu")
    await edit_or_reply(
        callback,
        "Введите верхнюю границу для Tier 1 (например, `6.0`):",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_limit_1)

@router.message(AdminStates.waiting_for_limit_1)
async def adm_save_limit_1(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        update_setting("tier_limit_1", str(val))
        await state.clear()
        await show_admin_menu(message, state)
    except ValueError:
        await edit_or_reply(message, "Введите число:", state=state)

@router.callback_query(F.data == "adm_set_limit_2")
async def adm_set_limit_2_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="adm_rates_menu")
    await edit_or_reply(
        callback,
        "Введите верхнюю границу для Tier 2 (например, `20.0`):",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_limit_2)

@router.message(AdminStates.waiting_for_limit_2)
async def adm_save_limit_2(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        update_setting("tier_limit_2", str(val))
        await state.clear()
        await show_admin_menu(message, state)
    except ValueError:
        await edit_or_reply(message, "Введите число:", state=state)

@router.callback_query(F.data == "adm_export_users")
async def adm_export_users(callback: CallbackQuery):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, username, balance, total_deals FROM users")
        users = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    file_content = f"{'USER_ID':<15} | {'USERNAME':<20} | {'BALANCE':<12} | {'DEALS':<6}\n"
    file_content += "-" * 63 + "\n"
    for uid, uname, bal, deals in users:
        uname_str = f"@{uname}" if uname else "none"
        file_content += f"{str(uid):<15} | {uname_str:<20} | {f'{bal} USDT':<12} | {str(deals):<6}\n"

    filename = "users_export.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(file_content)

    await callback.message.answer_document(
        document=FSInputFile(filename),
        caption="Табличный список пользователей системы:",
    )
    await callback.answer()

@router.callback_query(F.data == "adm_export_system_logs")
async def adm_export_system_logs(callback: CallbackQuery):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_audit=True) if hasattr(callback, 'show_audit') else await callback.answer("Недостаточно прав!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, user_id, username, action, created_at FROM system_logs ORDER BY id DESC"
        )
        logs = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    file_content = f"{'ID':<6} | {'USER_ID':<15} | {'USERNAME':<18} | {'ACTION':<35} | {'TIME':<19}\n"
    file_content += "-" * 105 + "\n"
    for l_id, uid, uname, action, created in logs:
        uname_str = f"@{uname}" if uname else "none"
        file_content += f"{f'#{l_id}':<6} | {str(uid):<15} | {uname_str:<18} | {str(action):<35} | {str(created):<19}\n"

    filename = "system_logs_export.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(file_content)

    await callback.message.answer_document(
        document=FSInputFile(filename), caption="Табличные системные логи:"
    )
    await callback.answer()

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())