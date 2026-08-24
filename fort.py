import asyncio
import logging
import random
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
import asyncpg

logging.basicConfig(level=logging.INFO)
TOKEN = "8919102783:AAFlB5ICuD7WzONLHzeW5dspJKj17TT7UMg"
ADMIN_ID = 8075312868

# Строка подключения к PostgreSQL
DATABASE_URL = "postgresql://postgres:TRKWhIlMeqpkMJBX@db.ycslyqhavhgproqrqvvs.supabase.co:5432/postgres"

SUPPORT_USERNAME = "@Derzywork"
REQUIRED_CHANNEL = "@FortunaPayNews"
REVIEWS_GROUP_ID = -1003589211301
REVIEWS_GROUP_USERNAME = "@FortunaPayRep"
LOG_CHANNEL_ID = -1004443604049

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# Глобальный пул соединений с базой данных
db_pool: asyncpg.Pool = None


# --- БАЗА ДАННЫХ (POSTGRESQL) ---
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:
        await conn.execute("""
                           CREATE TABLE IF NOT EXISTS settings
                           (
                               key
                               TEXT
                               PRIMARY
                               KEY,
                               value
                               TEXT
                           )
                           """)

        await conn.execute("""
                           CREATE TABLE IF NOT EXISTS users
                           (
                               user_id
                               BIGINT
                               PRIMARY
                               KEY,
                               username
                               TEXT,
                               balance
                               DOUBLE
                               PRECISION
                               DEFAULT
                               0.0,
                               total_deals
                               INTEGER
                               DEFAULT
                               0,
                               completed_deals
                               INTEGER
                               DEFAULT
                               0,
                               referrer_id
                               BIGINT
                               DEFAULT
                               NULL,
                               joined_date
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           )
                           """)

        await conn.execute("""
                           CREATE TABLE IF NOT EXISTS orders
                           (
                               id
                               SERIAL
                               PRIMARY
                               KEY,
                               user_id
                               BIGINT,
                               amount_usdt
                               DOUBLE
                               PRECISION,
                               amount_rub
                               DOUBLE
                               PRECISION,
                               check_link
                               TEXT,
                               phone
                               TEXT
                               DEFAULT
                               '',
                               bank
                               TEXT
                               DEFAULT
                               '',
                               fio
                               TEXT
                               DEFAULT
                               '',
                               status
                               TEXT
                               DEFAULT
                               'Ожидает администратора',
                               admin_id
                               BIGINT
                               DEFAULT
                               NULL,
                               sent_rub
                               DOUBLE
                               PRECISION
                               DEFAULT
                               0.0,
                               remainder_usdt
                               DOUBLE
                               PRECISION
                               DEFAULT
                               0.0,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           )
                           """)

        await conn.execute("""
                           CREATE TABLE IF NOT EXISTS system_logs
                           (
                               id
                               SERIAL
                               PRIMARY
                               KEY,
                               user_id
                               BIGINT,
                               username
                               TEXT,
                               action
                               TEXT,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           )
                           """)

        # Инициализация дефолтных настроек
        defaults = {
            'rate_tier_1': '80.0',
            'rate_tier_2': '90.0',
            'rate_tier_3': '120.0',
            'tier_limit_1': '6.0',
            'tier_limit_2': '20.0',
            'tier_limit_3': '80.0',
            'main_menu_photo': ''
        }
        for key, val in defaults.items():
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                key, val
            )


async def get_setting(key: str) -> str:
    async with db_pool.acquire() as conn:
        res = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
        return res if res is not None else ""


async def update_setting(key: str, value: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            key, value
        )


async def get_rate_for_amount(amount: float) -> tuple[float, float]:
    try:
        r1 = float(await get_setting("rate_tier_1"))
        r2 = float(await get_setting("rate_tier_2"))
        r3 = float(await get_setting("rate_tier_3"))
        lim1 = float(await get_setting("tier_limit_1"))
        lim2 = float(await get_setting("tier_limit_2"))
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
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO system_logs (user_id, username, action) VALUES ($1, $2, $3)",
                user_id, username, action,
            )
        except Exception as e:
            logging.error(f"Ошибка записи лога в БД: {e}")

    if not LOG_CHANNEL_ID:
        return
    try:
        user_mention = f"@{username}" if username else f"ID: `{user_id}`"
        log_text = (
            f"Лог системы FortunaPay\n\nПользователь:"
            f" {user_mention}\nID: `{user_id}`\nДействие: {action}"
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
    waiting_for_requisites = State()


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
            icon_custom_emoji_id="5920090136627908485",
        )
    builder.button(
        text="Проверить подписку",
        callback_data="check_sub",
        icon_custom_emoji_id="5920052658743283381",
    )
    builder.adjust(1)
    return builder.as_markup()


def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Личный кабинет",
        callback_data="profile",
        icon_custom_emoji_id="5883964170268840032",
    )
    builder.button(
        text="Продать USDT",
        callback_data="sell_usdt",
        icon_custom_emoji_id="5992430854909989581",
    )
    builder.button(
        text="Калькулятор",
        callback_data="calculator",
        icon_custom_emoji_id="5935938364086685805",
    )
    builder.button(
        text="Актуальные курсы",
        callback_data="exchange_rate",
        icon_custom_emoji_id="5994378914636500516",
    )
    builder.button(
        text="Мои заявки",
        callback_data="history",
        icon_custom_emoji_id="5967456680940671207",
    )
    builder.button(
        text="Рефералы",
        callback_data="referral_menu",
        icon_custom_emoji_id="5877530150345641603",
    )
    builder.button(
        text="Отзывы",
        callback_data="reviews",
        icon_custom_emoji_id="5958376256788502078",
    )
    builder.button(
        text="Поддержка",
        url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}",
        icon_custom_emoji_id="5778575233422200567",
    )
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def menu_button_kb():
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Главное меню",
        callback_data="main_menu",
        icon_custom_emoji_id="6008258140108231117",
    )
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

    async with db_pool.acquire() as conn:
        exists = await conn.fetchrow(
            "SELECT user_id, referrer_id FROM users WHERE user_id = $1", user_id
        )
        if not exists:
            await conn.execute(
                "INSERT INTO users (user_id, username, referrer_id) VALUES ($1, $2, $3)",
                user_id, username, referrer_id,
            )
        else:
            current_ref = exists["referrer_id"]
            if not current_ref and referrer_id and referrer_id != user_id:
                await conn.execute(
                    "UPDATE users SET referrer_id = $1 WHERE user_id = $2",
                    referrer_id, user_id,
                )
            await conn.execute(
                "UPDATE users SET username = $1 WHERE user_id = $2", username, user_id
            )

    if not await check_subscription(user_id):
        text = (
            "[🔒](tg://emoji?id=5920090136627908485) **Требуется подписка**\n\nДля"
            f" использования сервиса подпишитесь на официальный канал:"
            f" `{REQUIRED_CHANNEL}`\n\nПосле подписки нажмите кнопку проверки ниже:"
        )
        await edit_or_reply(event, text, reply_markup=sub_check_kb(), state=state)
        return

    if isinstance(event, Message):
        await send_log(user_id, username, "Запустил бота / Главное меню")

    menu_text = (
        "👋 Добро пожаловать в FortunaPay!\n\n💱 Быстрый и надёжный обмен USDT →"
        " RUB.\n\nВыберите действие в меню ниже:"
    )

    menu_photo = await get_setting("main_menu_photo")
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
        menu_photo = await get_setting("main_menu_photo")
        text = (
            "[✅](tg://emoji?id=5776375003280838798) Подписка подтверждена!\n\nГлавное"
            " меню:"
        )
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
        "[⭐](tg://emoji?id=5958376256788502078) **Отзывы о сервисе FortunaPay**"
        " [💬](tg://emoji?id=5778575233422200567)\n\nВы можете ознакомиться с"
        " реальными отзывами наших клиентов или оставить свой собственный"
        " отзыв сразу после завершения успешного обмена!"
        " [🔥](tg://emoji?id=5994378914636500516)"
    )

    builder = InlineKeyboardBuilder()
    if REVIEWS_GROUP_USERNAME:
        builder.button(
            text="Почитать отзывы в канале",
            url=f"https://t.me/{REVIEWS_GROUP_USERNAME.replace('@', '')}",
            icon_custom_emoji_id="5931628549088744687",
        )
    builder.button(
        text="Главное меню",
        callback_data="main_menu",
        icon_custom_emoji_id="6008258140108231117",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "profile")
async def user_profile(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    username = callback.from_user.username
    await send_log(user_id, username, "Открыл профиль")

    async with db_pool.acquire() as conn:
        res = await conn.fetchrow(
            "SELECT balance, total_deals, completed_deals, joined_date FROM users WHERE user_id = $1",
            user_id,
        )

    if res:
        balance, total, completed, joined = res["balance"], res["total_deals"], res["completed_deals"], str(
            res["joined_date"])
    else:
        balance, total, completed, joined = 0.0, 0, 0, "Неизвестно"

    profile_text = (
        f"[👤](tg://emoji?id=5883964170268840032) **Личный кабинет**"
        f" [✨](tg://emoji?id=5994378914636500516)\n\n[🆔](tg://emoji?id=5994378914636500516)"
        f" ID: `{user_id}`\n[💬](tg://emoji?id=5778575233422200567) Юзернейм:"
        f" @{username if username else 'отсутствует'}\n[📅](tg://emoji?id=5967456680940671207)"
        f" Регистрация: `{joined}`\n\n[📊](tg://emoji?id=5931515758952583071)"
        f" **Статистика сделок:** [📈](tg://emoji?id=5931515758952583071)\n[🪙](tg://emoji?id=5992430854909989581)"
        f" Баланс аккаунта: `{balance:.2f} USDT`"
        f" [💎](tg://emoji?id=5994378914636500516)\n[📁](tg://emoji?id=5935938364086685805)"
        f" Всего заявок: `{total}` (Успешно: `{completed}`)"
        f" [🔥](tg://emoji?id=5992430854909989581)"
    )

    await edit_or_reply(
        callback, profile_text, reply_markup=menu_button_kb(), state=state
    )


@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    async with db_pool.acquire() as conn:
        ref_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1", user_id)

    text = (
        f"[🎁](tg://emoji?id=5877530150345641603) **Реферальная система (3%)**"
        f" [💎](tg://emoji?id=5994378914636500516)\n\nПриглашайте друзей и получайте"
        f" **3%** от суммы их успешных обменов прямо на ваш баланс!"
        f" [🚀](tg://emoji?id=5935938364086685805)\n\n[🔗](tg://emoji?id=5931515758952583071)"
        f" **Ваша реферальная ссылка:**\n`{ref_link}`\n\n[👥](tg://emoji?id=5883964170268840032)"
        f" Приглашено пользователей: `{ref_count}`"
        f" [🔥](tg://emoji?id=5992430854909989581)"
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "calculator")
async def calculator_start(callback: CallbackQuery, state: FSMContext):
    await send_log(
        callback.from_user.id, callback.from_user.username, "Открыл калькулятор"
    )
    r1 = await get_setting("rate_tier_1")
    r2 = await get_setting("rate_tier_2")
    r3 = await get_setting("rate_tier_3")
    lim1 = await get_setting("tier_limit_1")
    lim2 = await get_setting("tier_limit_2")

    text = (
        "[🧮](tg://emoji?id=5935938364086685805) **Калькулятор USDT ➔ RUB**"
        f" [📊](tg://emoji?id=5931515758952583071)\n\nДействующие тарифные"
        f" ставки:\n[🔹](tg://emoji?id=5883964170268840032) • До {lim1} USDT ➔"
        f" `{r1} ₽`\n[🔹](tg://emoji?id=5883964170268840032) • От {lim1} до"
        f" {lim2} USDT ➔ `{r2} ₽`\n[🔹](tg://emoji?id=5883964170268840032) • От"
        f" {lim2} USDT ➔ `{r3} ₽`\n\n[💬](tg://emoji?id=5778575233422200567)"
        " Отправляйте числа сообщением — сумма будет пересчитываться"
        " автоматически:"
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
        text = (
            "Некорректная сумма.\n\nВведите число (например, `5` или `50.5`):"
        )
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    rate, _ = await get_rate_for_amount(amount)
    total_rub = round(amount * rate, 2)

    text = (
        f"[📈](tg://emoji?id=5931515758952583071) **Результат расчета:**"
        f" [🪙](tg://emoji?id=5992430854909989581)\n\nСумма к обмену: `{amount}"
        f" USDT`\nПримененный курс: `{rate} ₽` / USDT\nВы получите: `{total_rub} ₽`"
        " [🔥](tg://emoji?id=5994378914636500516)\n\n*Можете отправить другое число"
        " для мгновенного пересчета:*"
    )

    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "sell_usdt")
async def sell_usdt_start(callback: CallbackQuery, state: FSMContext):
    await send_log(
        callback.from_user.id,
        callback.from_user.username,
        "Начал создание заявки на продажу",
    )

    r1 = await get_setting("rate_tier_1")
    r2 = await get_setting("rate_tier_2")
    r3 = await get_setting("rate_tier_3")
    lim1 = await get_setting("tier_limit_1")
    lim2 = await get_setting("tier_limit_2")

    text = (
        f"[💎](tg://emoji?id=5994378914636500516) **Создание заявки на обмен**"
        f" [🚀](tg://emoji?id=5935938364086685805)\n\n[📊](tg://emoji?id=5931515758952583071)"
        f" Действующие курсы:\n[🔹](tg://emoji?id=5883964170268840032) • До"
        f" {lim1}$ ➔ `{r1} ₽`\n[🔹](tg://emoji?id=5883964170268840032) •"
        f" {lim1}-{lim2}$ ➔ `{r2} ₽`\n[🔹](tg://emoji?id=5883964170268840032) • От"
        f" {lim2}$ ➔ `{r3} ₽`\n\n[🪙](tg://emoji?id=5992430854909989581) Отправьте"
        " сообщением сумму USDT, которую хотите обменять:"
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
        text = (
            "Ошибка ввода. Введите корректное число USDT (например, `10` или"
            " `25.5`):"
        )
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    user_id = message.from_user.id
    async with db_pool.acquire() as conn:
        user_balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id)
        user_balance = user_balance if user_balance is not None else 0.0

    rate, _ = await get_rate_for_amount(amount)
    total_rub = round(amount * rate, 2)

    await state.update_data(
        amount_usdt=amount, amount_rub=total_rub, user_balance=user_balance
    )

    if user_balance > 0:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"Списать с баланса ({min(user_balance, amount):.2f} USDT)",
            callback_data="use_balance_yes",
            icon_custom_emoji_id="5778318458802409852",
        )
        builder.button(
            text="Оплатить полностью через чек",
            callback_data="use_balance_no",
            icon_custom_emoji_id="5992430854909989581",
        )
        builder.button(
            text="Главное меню",
            callback_data="main_menu",
            icon_custom_emoji_id="6008258140108231117",
        )
        builder.adjust(1)

        text = (
            f"[🪙](tg://emoji?id=5992430854909989581) Обнаружен внутренний баланс:"
            f" `{user_balance:.2f} USDT`\n\nЖелаете ли вы использовать средства с"
            f" баланса для частичной или полной оплаты заявки на `{amount} USDT`?"
        )
        await edit_or_reply(
            message, text, reply_markup=builder.as_markup(), state=state
        )
        await state.set_state(SellStates.waiting_for_balance_choice)
    else:
        text = (
            f"Заявка: {amount} USDT (`{total_rub} ₽`)\nКурс: `{rate} ₽` /"
            f" USDT\n\nШаг 1 из 2: Отправьте ссылку на чек из"
            " @CryptoBot\n*(Пример: `https://t.me/CryptoBot?start=...`)*:"
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
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                    amount_usdt, user_id,
                )
                order_id = await conn.fetchval(
                    """
                    INSERT INTO orders (user_id, amount_usdt, amount_rub, check_link, status)
                    VALUES ($1, $2, $3, 'Оплачено с баланса', 'Ожидает реквизиты') RETURNING id
                    """,
                    user_id, amount_usdt, amount_rub,
                )
                await conn.execute(
                    "UPDATE users SET total_deals = total_deals + 1 WHERE user_id = $1",
                    user_id,
                )

        await state.update_data(order_id=order_id, check_link="Оплачено с баланса")

        text = (
            "Оплата с баланса успешна!\n\nШаг 2 из 2: Укажите реквизиты для получения"
            " оплаты\n\nОтправьте сообщением данные:\n• Номер телефона / карты\n•"
            " Название банка\n• ФИО получателя\n\n*(Пример: `+79991234567, Т-Банк,"
            " Иванов Иван И.`)*"
        )
        await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
        await state.set_state(SellStates.waiting_for_requisites)
    else:
        link_instruction = (
            f"С баланса списано `{used_from_balance:.2f} USDT`. Остаток нужно"
            " доплатить через чек."
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
    if "t.me" not in check_link.lower() and "http" not in check_link.lower():
        text = (
            "Некорректная ссылка на чек.\n\nПожалуйста, отправьте валидную ссылку из"
            " `@CryptoBot`\n*(Пример: `https://t.me/CryptoBot?start=...`)*:"
        )
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    data = await state.get_data()
    amount_usdt = data.get("amount_usdt")
    amount_rub = data.get("amount_rub")
    used_from_balance = data.get("used_from_balance", 0.0)
    user_id = message.from_user.id

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            if used_from_balance > 0:
                await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                    used_from_balance, user_id,
                )

            order_id = await conn.fetchval(
                """
                INSERT INTO orders (user_id, amount_usdt, amount_rub, check_link, status)
                VALUES ($1, $2, $3, $4, 'Ожидает реквизиты') RETURNING id
                """,
                user_id, amount_usdt, amount_rub, check_link,
            )

    await state.update_data(order_id=order_id, check_link=check_link)

    text = (
        "Ссылка принята!\n\nШаг 2 из 2: Укажите реквизиты для получения"
        " оплаты\n\nОтправьте сообщением данные:\n• Номер телефона / карты\n•"
        " Название банка\n• ФИО получателя\n\n*(Пример: `+79991234567, Т-Банк,"
        " Иванов Иван И.`)*"
    )
    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_requisites)


@router.message(SellStates.waiting_for_requisites)
async def process_sell_requisites(message: Message, state: FSMContext):
    raw_req = message.text.strip()

    if len(raw_req) < 5:
        text = (
            "Слишком короткий текст. Укажите подробные реквизиты (Телефон, Банк,"
            " ФИО):"
        )
        await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
        return

    parts = raw_req.replace(",", " ").split()
    phone = parts[0] if len(parts) > 0 else "Указано в данных"
    bank = parts[1] if len(parts) > 1 else "Указано в данных"
    fio = " ".join(parts[2:]) if len(parts) > 2 else raw_req

    data = await state.get_data()
    order_id = data.get("order_id")
    amount_usdt = data.get("amount_usdt")
    amount_rub = data.get("amount_rub")
    check_link = data.get("check_link")
    used_from_balance = data.get("used_from_balance", 0.0)

    user_id = message.from_user.id
    username = message.from_user.username

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE orders
                SET phone  = $1,
                    bank   = $2,
                    fio    = $3,
                    status = 'Ожидает администратора'
                WHERE id = $4
                """,
                phone, bank, fio, order_id,
            )
            await conn.execute(
                "UPDATE users SET total_deals = total_deals + 1 WHERE user_id = $1",
                user_id,
            )

    await send_log(
        user_id, username, f"Создал заявку #{order_id} на сумму {amount_usdt} USDT"
    )

    balance_note = (
        f"\nСписано с баланса: `{used_from_balance:.2f} USDT`"
        if used_from_balance > 0
        else ""
    )
    success_text = (
        f"Заявка #{order_id} полностью сформирована!\n\nСумма: `{amount_usdt} USDT`"
        f" (`{amount_rub} ₽`){balance_note}\nРеквизиты: `{raw_req}`\n\nСтатус:"
        " **Ожидает обработку администратором...**"
    )
    await edit_or_reply(message, success_text, reply_markup=main_menu_kb(), state=state)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Взять заявку",
        callback_data=f"take_order_{order_id}",
        icon_custom_emoji_id="5906995262378741881",
    )

    admin_text = (
        f"🔔 **НОВАЯ ЗАЯВКА #{order_id} ГОТОВА К ОБРАБОТКЕ!**\n\nПользователь:"
        f" @{username} (`{user_id}`)\nСумма: `{amount_usdt} USDT` (`{amount_rub}"
        f" ₽`){balance_note}\nРеквизиты: `{raw_req}`\nЧек: {check_link}"
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
    async with db_pool.acquire() as conn:
        res = await conn.fetchrow("SELECT status, user_id FROM orders WHERE id = $1", order_id)

        if not res:
            await callback.answer("Заявка не найдена в базе.", show_alert=True)
            return

        status, client_id = res["status"], res["user_id"]
        if status not in ("Ожидает администратора", "Ожидает реквизиты"):
            await callback.answer(
                f"Заявка уже обработана или находится в статусе: {status}",
                show_alert=True,
            )
            return

        await conn.execute(
            "UPDATE orders SET status = 'В работе', admin_id = $1 WHERE id = $2",
            callback.from_user.id, order_id,
        )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Ввести отправленную сумму",
        callback_data=f"pay_order_{order_id}",
        icon_custom_emoji_id="5994297722574737553",
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
            text=(
                f"Ваша заявка #{order_id} взята в обработку администратором! Идет"
                " проверка чека и выплата."
            ),
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
        icon_custom_emoji_id="5778527486270770928",
    )

    await edit_or_reply(
        callback,
        f"Введите фактически переведенную сумму в рублях (`RUB`) для заявки"
        f" **#{order_id}**:",
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

    async with db_pool.acquire() as conn:
        res = await conn.fetchrow(
            "SELECT user_id, amount_rub, amount_usdt FROM orders WHERE id = $1",
            order_id,
        )

        if not res:
            await edit_or_reply(
                message,
                "Заявка не найдена.",
                reply_markup=menu_button_kb(),
                state=state,
            )
            await state.clear()
            return

        client_id, expected_rub, amount_usdt = res["user_id"], res["amount_rub"], res["amount_usdt"]

        if sent_rub < expected_rub:
            remainder_rub = round(expected_rub - sent_rub, 2)
            rate, _ = await get_rate_for_amount(amount_usdt)
            remainder_usdt = round(remainder_rub / rate, 2)

            await conn.execute(
                "UPDATE orders SET sent_rub = $1, remainder_usdt = $2, status = 'Ожидает решения по остатку' WHERE id = $3",
                sent_rub, remainder_usdt, order_id,
            )

            builder = InlineKeyboardBuilder()
            builder.button(
                text="Зачислить остаток на баланс ($)",
                callback_data=f"usr_rem_balance_{order_id}",
                icon_custom_emoji_id="5769403330761593044",
            )
            builder.button(
                text="Оставить на чай",
                callback_data=f"usr_rem_tip_{order_id}",
                icon_custom_emoji_id="5899833370052923106",
            )
            builder.adjust(1)

            user_text = (
                f"Выплата по заявке #{order_id} частичная!\n\nПереведено: `{sent_rub}"
                f" ₽` из `{expected_rub} ₽`\nНедоплата составила: `{remainder_rub} ₽`"
                f" (≈ `{remainder_usdt} USDT`)\n\nУкажите, как поступить с остатком"
                " средств:"
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
                    f"Перевод зафиксирован частично (`{sent_rub} ₽`). Запрос решений"
                    f" отправлен клиенту #{client_id}.",
                    state=state,
                )
            except Exception as e:
                logging.error(f"Ошибка уведомления клиента: {e}")
        else:
            await conn.execute(
                "UPDATE orders SET sent_rub = $1, status = 'Ожидает подтверждения' WHERE id = $2",
                sent_rub, order_id,
            )

            await finalize_payout(bot, client_id, sent_rub, order_id)
            await edit_or_reply(
                message,
                f"Выплата по заявке #{order_id} на сумму {sent_rub} ₽ проведена.",
                state=state,
            )

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

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.fetchrow(
                "SELECT remainder_usdt, sent_rub FROM orders WHERE id = $1 AND user_id = $2",
                order_id, user_id,
            )

            if not res:
                await callback.answer("Заявка не найдена.", show_alert=True)
                return

            remainder_usdt, sent_rub = res["remainder_usdt"], res["sent_rub"]

            if action == "balance":
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    remainder_usdt, user_id,
                )
                choice_text = (
                    f"Остаток `{remainder_usdt:.2f} USDT` успешно зачислен на ваш"
                    " внутренний баланс!"
                )
            else:
                await conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('total_tips_usdt', '0') ON CONFLICT (key) DO NOTHING"
                )
                await conn.execute(
                    "UPDATE settings SET value = (CAST(value AS REAL) + $1)::TEXT WHERE key = 'total_tips_usdt'",
                    remainder_usdt,
                )
                choice_text = (
                    "Большое спасибо! Остаток передан в качестве чаевых."
                )

            await conn.execute(
                "UPDATE orders SET status = 'Ожидает подтверждения' WHERE id = $1",
                order_id,
            )

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
        icon_custom_emoji_id="5776375003280838798",
    )
    builder.button(
        text="Деньги не пришли",
        callback_data=f"confirm_no_{order_id}",
        icon_custom_emoji_id="5778527486270770928",
    )
    builder.adjust(2)

    extra_block = f"{extra_text}\n" if extra_text else ""
    text = (
        f"Выплата по заявке #{order_id} отправлена!\n\nСумма перевода:`{sent_rub}`"
        f" ₽\n{extra_block}\nПожалуйста, проверьте баланс карты и подтвердите"
        " получение:"
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

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.fetchrow(
                "SELECT status, amount_usdt FROM orders WHERE id = $1 AND user_id = $2",
                order_id, user_id,
            )

            if not res:
                await callback.answer("Заявка не найдена.", show_alert=True)
                return

            status, amount_usdt = res["status"], res["amount_usdt"]
            if status == "Завершено":
                await callback.answer("Сделка уже подтверждена ранее.", show_alert=True)
                return

            await conn.execute(
                "UPDATE orders SET status = 'Завершено' WHERE id = $1", order_id
            )
            await conn.execute(
                "UPDATE users SET completed_deals = completed_deals + 1 WHERE user_id = $1",
                user_id,
            )

            ref_res = await conn.fetchrow(
                "SELECT referrer_id FROM users WHERE user_id = $1", user_id
            )
            if ref_res and ref_res["referrer_id"]:
                referrer_id = ref_res["referrer_id"]
                bonus = round(amount_usdt * 0.03, 4)
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    bonus, referrer_id,
                )
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            "Реферальный бонус!\nПользователь по вашей ссылке успешно"
                            f" завершил обмен. Вам начислено `{bonus} USDT` (3%)."
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

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
        icon_custom_emoji_id="5771511103141975115",
    )

    await edit_or_reply(
        callback,
        f"Сделка #{order_id} успешно завершена!\n\nНапишите короткий отзыв о"
        " работе сервиса FortunaPay ниже:",
        reply_markup=builder.as_markup(),
        state=state,
    )

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=(
                "Пользователь подтвердил получение средств по заявке"
                f" #{order_id}. Сделка закрыта!"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


@router.callback_query(F.data == "skip_review")
async def skip_review_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    menu_photo = await get_setting("main_menu_photo")
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
        f"Новый отзыв о FortunaPay\n\nОт: {user_mention}\nДата:"
        f" `{current_date}`\n\nКомментарий:\n{review_text}"
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

    menu_photo = await get_setting("main_menu_photo")
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
        icon_custom_emoji_id="5778575233422200567",
    )
    builder.button(
        text="Главное меню",
        callback_data="main_menu",
        icon_custom_emoji_id="6008258140108231117",
    )
    builder.adjust(1)

    instruction_text = (
        f"Фиксация проблемы по заявке #{order_id}\n\nДля решения диспута запишите"
        f" видео экрана:\n\n1. Откройте мобильное приложение банка\n2. Покажите"
        f" привязанный номер СБП\n3. Пролистайте историю операций за"
        f" сегодня\n4. Откройте чек любой последней операции\n5. Напишите код"
        f" `{random_code}` в любом поле ввода\n\nОтправьте запись администратору"
        " поддержки."
    )

    await edit_or_reply(
        callback, instruction_text, reply_markup=builder.as_markup(), state=state
    )

    try:
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=(
                f"ВНИМАНИЕ! Диспут по заявке #{order_id}. Клиент указал, что деньги"
                f" не пришли (Код проверки: {random_code})"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


@router.callback_query(F.data == "exchange_rate")
async def exchange_rate_handler(callback: CallbackQuery, state: FSMContext):
    await send_log(
        callback.from_user.id, callback.from_user.username, "Посмотрел курс"
    )
    r1 = await get_setting("rate_tier_1")
    r2 = await get_setting("rate_tier_2")
    r3 = await get_setting("rate_tier_3")
    lim1 = await get_setting("tier_limit_1")
    lim2 = await get_setting("tier_limit_2")

    text = (
        f"[📊](tg://emoji?id=5931515758952583071) **Актуальные курсы обмена**"
        f" [🪙](tg://emoji?id=5992430854909989581)\n\n[🔹](tg://emoji?id=5883964170268840032)"
        f" • До {lim1} USDT ➔ `{r1} ₽` за 1 USDT\n[🔹](tg://emoji?id=5883964170268840032)"
        f" • От {lim1} до {lim2} USDT ➔ `{r2} ₽` за 1"
        f" USDT\n[🔹](tg://emoji?id=5883964170268840032) • От {lim2} USDT ➔"
        f" `{r3} ₽` за 1 USDT\n\n[ℹ️](tg://emoji?id=5935938364086685805) Расчет"
        " курса пересчитывается автоматически."
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "history")
async def history_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await send_log(user_id, callback.from_user.username, "Просмотр истории")

    async with db_pool.acquire() as conn:
        totals = await conn.fetchrow(
            "SELECT COUNT(*), SUM(CASE WHEN status = 'Завершено' THEN 1 ELSE 0 END) FROM orders WHERE user_id = $1",
            user_id,
        )
        total_q = totals[0] if totals[0] is not None else 0
        completed_q = totals[1] if totals[1] is not None else 0

        orders = await conn.fetch(
            "SELECT id, amount_usdt, amount_rub, status FROM orders WHERE user_id = $1 ORDER BY id DESC LIMIT 5",
            user_id,
        )

    text = (
        f"[📁](tg://emoji?id=5935938364086685805) **История ваших операций**"
        f" [📊](tg://emoji?id=5931515758952583071)\n\nВсего заявок: `{total_q}` |"
        " Завершено: `{completed_q}`\n\nПоследние действия:"
    )

    builder = InlineKeyboardBuilder()
    if orders:
        for row in orders:
            builder.button(
                text=f"#{row['id']} | {row['amount_usdt']} USDT ({row['status']})",
                callback_data=f"view_order_{row['id']}",
                icon_custom_emoji_id="5992430854909989581",
            )

    builder.button(
        text="Главное меню",
        callback_data="main_menu",
        icon_custom_emoji_id="6008258140108231117",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data.startswith("view_order_"))
async def view_order_details(callback: CallbackQuery, state: FSMContext):
    o_id = int(callback.data.split("_")[-1])
    async with db_pool.acquire() as conn:
        res = await conn.fetchrow(
            "SELECT amount_usdt, amount_rub, status, check_link, phone, bank, fio, created_at FROM orders WHERE id = $1 AND user_id = $2",
            o_id, callback.from_user.id,
        )

    if not res:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    text = (
        f"Детали заявки #{o_id}\n\nСумма: `{res['amount_usdt']} USDT`\nОжидается к выплате:"
        f" `{res['amount_rub']} ₽`\nТелефон: `{res['phone']}`\nБанк: `{res['bank']}`\nФИО: `{res['fio']}`\nТекущий"
        f" статус: `{res['status']}`\nЧек: {res['check_link']}\nВремя создания: `{res['created_at']}`"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="К истории",
        callback_data="history",
        icon_custom_emoji_id="5956561916573782596",
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

    async with db_pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        pending_count = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE status IN ('Ожидает администратора', 'Ожидает реквизиты')"
        )
        in_progress_count = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE status IN ('В работе', 'Ожидает решения по остатку', 'Ожидает подтверждения')"
        )
        completed_count = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'Завершено'")
        tip_res = await conn.fetchval("SELECT value FROM settings WHERE key = 'total_tips_usdt'")
        total_tips = float(tip_res) if tip_res else 0.0

    r1 = await get_setting("rate_tier_1")
    r2 = await get_setting("rate_tier_2")
    r3 = await get_setting("rate_tier_3")
    lim1 = await get_setting("tier_limit_1")
    lim2 = await get_setting("tier_limit_2")

    text = (
        f"Панель управления сервисом FortunaPay\n\nВсего пользователей:"
        f" `{users_count}`\nНовые заявки: `{pending_count}`\nАктивные заявки в"
        f" работе: `{in_progress_count}`\nУспешно завершено сделок:"
        f" `{completed_count}`\n💰 Всего оставили на чай: `{total_tips:.2f}"
        f" USDT`\n\nТекущие курсы и лимиты:\n• До {lim1}$ ➔ `{r1} ₽`\n•"
        f" {lim1}-{lim2}$ ➔ `{r2} ₽`\n• От {lim2}$ ➔ `{r3} ₽`"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Ожидают ({pending_count})",
        callback_data="adm_pending_orders",
        icon_custom_emoji_id="5942640218170461901",
    )
    builder.button(
        text=f"В работе ({in_progress_count})",
        callback_data="adm_in_progress_orders",
        icon_custom_emoji_id="5943042214224465443",
    )
    builder.button(
        text="Завершенные сделки",
        callback_data="adm_completed_orders",
        icon_custom_emoji_id="5933613451044720529",
    )
    builder.button(
        text="Изменить баланс юзера",
        callback_data="adm_edit_balance_start",
        icon_custom_emoji_id="5992430854909989581",
    )
    builder.button(
        text="Изменить курсы/лимиты",
        callback_data="adm_rates_menu",
        icon_custom_emoji_id="5931515758952583071",
    )
    builder.button(
        text="🖼 Изменить фото меню",
        callback_data="adm_set_menu_photo",
        icon_custom_emoji_id="5992430854909989581",
    )
    builder.button(
        text="Рассылка",
        callback_data="adm_broadcast",
        icon_custom_emoji_id="5771695636411847302",
    )
    builder.button(
        text="Выгрузить юзеров (TXT)",
        callback_data="adm_export_users",
        icon_custom_emoji_id="5908808657700655253",
    )
    builder.button(
        text="Выгрузить логи (TXT)",
        callback_data="adm_export_system_logs",
        icon_custom_emoji_id="6017174676898321263",
    )
    builder.button(
        text="Выход в меню",
        callback_data="main_menu",
        icon_custom_emoji_id="6008258140108231117",
    )
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
    builder.button(
        text="Удалить текущее фото",
        callback_data="adm_clear_menu_photo",
        icon_custom_emoji_id="5778527486270770928",
    )
    builder.button(
        text="Отмена",
        callback_data="adm_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
    builder.adjust(1)
    await edit_or_reply(
        callback,
        "Отправьте картинку (фотографию), которая будет отображаться в главном"
        " меню бота:",
        reply_markup=builder.as_markup(),
        state=state,
    )
    await state.set_state(AdminStates.waiting_for_menu_photo)


@router.callback_query(F.data == "adm_clear_menu_photo")
async def adm_clear_menu_photo(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    await update_setting("main_menu_photo", "")
    await state.clear()
    await callback.answer("Фотография главного меню удалена!", show_alert=True)
    await show_admin_menu(callback, state)


@router.message(AdminStates.waiting_for_menu_photo, F.photo)
async def adm_save_menu_photo(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    photo_id = message.photo[-1].file_id
    await update_setting("main_menu_photo", photo_id)
    await state.clear()
    await message.answer("Фотография главного меню успешно обновлена!")
    await show_admin_menu(message, state)


@router.message(AdminStates.waiting_for_menu_photo)
async def adm_wrong_menu_photo(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return
    await message.answer(
        "Пожалуйста, отправьте именно **изображение (фото)** или нажмите кнопку"
        " отмены:"
    )


@router.callback_query(F.data == "adm_edit_balance_start")
async def adm_edit_balance_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отмена",
        callback_data="adm_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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

    async with db_pool.acquire() as conn:
        res = await conn.fetchrow(
            "SELECT balance, username FROM users WHERE user_id = $1", target_id
        )

    if not res:
        await message.answer(
            f"Пользователь с ID `{target_id}` не найден в базе данных.",
            parse_mode="Markdown",
        )
        return

    await state.update_data(target_id=target_id)
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отмена",
        callback_data="adm_menu",
        icon_custom_emoji_id="5778527486270770928",
    )

    await edit_or_reply(
        message,
        f"Пользователь: @{res['username'] or 'отсутствует'} (`{target_id}`)\nТекущий баланс:"
        f" `{res['balance']:.2f} USDT`\n\nВведите новое значение баланса (число,"
        " например `15.5` или `0`):",
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

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = $1 WHERE user_id = $2", new_balance, target_id
        )

    await state.clear()
    await message.answer(
        f"Баланс пользователя `{target_id}` успешно изменен на `{new_balance:.2f}"
        " USDT`!",
        parse_mode="Markdown",
    )

    try:
        await bot.send_message(
            chat_id=target_id,
            text=(
                "Администратор обновил ваш баланс. Текущий баланс:"
                f" `{new_balance:.2f} USDT`"
            ),
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
    builder.button(
        text="Курс (1)",
        callback_data="adm_set_rate_1",
        icon_custom_emoji_id="5931515758952583071",
    )
    builder.button(
        text="Курс (2)",
        callback_data="adm_set_rate_2",
        icon_custom_emoji_id="5931515758952583071",
    )
    builder.button(
        text="Курс (3)",
        callback_data="adm_set_rate_3",
        icon_custom_emoji_id="5931515758952583071",
    )
    builder.button(
        text="Лимит 1",
        callback_data="adm_set_limit_1",
        icon_custom_emoji_id="5924720918826848520",
    )
    builder.button(
        text="Лимит 2",
        callback_data="adm_set_limit_2",
        icon_custom_emoji_id="5924720918826848520",
    )
    builder.button(
        text="Назад",
        callback_data="adm_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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

    async with db_pool.acquire() as conn:
        orders = await conn.fetch("""
                                  SELECT id,
                                         user_id,
                                         amount_usdt,
                                         amount_rub,
                                         phone,
                                         bank,
                                         fio,
                                         status,
                                         check_link
                                  FROM orders
                                  WHERE status IN ('Ожидает администратора', 'Ожидает реквизиты')
                                  ORDER BY id ASC
                                  """)

    if not orders:
        await callback.answer("Нет нераспределенных заявок.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    text = "Необработанные заявки:\n\n"
    for row in orders:
        req_info = (
            f"📞 `{row['phone']}` | 🏦 `{row['bank']}` | 👤 `{row['fio']}`"
            if row['phone']
            else "*Реквизиты еще не введены*"
        )
        text += (
            f"🆔 **#{row['id']}** [{row['status']}] | `{row['amount_usdt']} USDT` (`{row['amount_rub']} ₽`)\n🔗 Чек:"
            f" {row['check_link']}\n{req_info}\n\n"
        )
        builder.button(
            text=f"Взять #{row['id']}",
            callback_data=f"take_order_{row['id']}",
            icon_custom_emoji_id="5906995262378741881",
        )

    builder.button(
        text="Панель управления",
        callback_data="adm_menu",
        icon_custom_emoji_id="5775887550262546277",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_in_progress_orders")
async def adm_in_progress_orders(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        orders = await conn.fetch("""
                                  SELECT id,
                                         user_id,
                                         amount_usdt,
                                         amount_rub,
                                         phone,
                                         bank,
                                         fio,
                                         status
                                  FROM orders
                                  WHERE status IN ('В работе', 'Ожидает решения по остатку', 'Ожидает подтверждения')
                                  ORDER BY id DESC
                                  """)

    if not orders:
        await callback.answer("Нет активных процессов.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    text = "Заявки в обработке:\n\n"
    for row in orders:
        text += (
            f"🆔 **#{row['id']}** [{row['status']}] | `{row['amount_usdt']} USDT` (`{row['amount_rub']} ₽`)\n📞 `{row['phone']}` |"
            f" 🏦 `{row['bank']}` | 👤 `{row['fio']}`\n\n"
        )
        builder.button(
            text=f"Перевод по #{row['id']}",
            callback_data=f"pay_order_{row['id']}",
            icon_custom_emoji_id="5897958754267174109",
        )

    builder.button(
        text="Панель управления",
        callback_data="adm_menu",
        icon_custom_emoji_id="5775887550262546277",
    )
    builder.adjust(1)

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_completed_orders")
async def adm_completed_orders(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        orders = await conn.fetch("""
                                  SELECT id, user_id, amount_usdt, amount_rub, sent_rub
                                  FROM orders
                                  WHERE status = 'Завершено'
                                  ORDER BY id DESC LIMIT 15
                                  """)

    if not orders:
        await callback.answer("Завершенных сделок пока нет.", show_alert=True)
        return

    text = "История последних выполненных сделок:\n\n"
    for row in orders:
        text += (
            f"🆔 **#{row['id']}** | ID Клиента: `{row['user_id']}` | `{row['amount_usdt']} USDT` ➔"
            f" `{row['sent_rub'] or row['amount_rub']} ₽`\n"
        )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Панель управления",
        callback_data="adm_menu",
        icon_custom_emoji_id="5775887550262546277",
    )

    await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != int(ADMIN_ID):
        return
    data = await state.get_data()
    await state.update_data(main_msg_id=data.get("main_msg_id"))
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отмена",
        callback_data="adm_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")

    success, failed = 0, 0
    await message.answer("Рассылка запущена...")
    for row in users:
        try:
            await bot.send_message(chat_id=row['user_id'], text=text, parse_mode="Markdown")
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
    builder.button(
        text="Отмена",
        callback_data="adm_rates_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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
        await update_setting("rate_tier_1", str(val))
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
    builder.button(
        text="Отмена",
        callback_data="adm_rates_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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
        await update_setting("rate_tier_2", str(val))
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
    builder.button(
        text="Отмена",
        callback_data="adm_rates_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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
        await update_setting("rate_tier_3", str(val))
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
    builder.button(
        text="Отмена",
        callback_data="adm_rates_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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
        await update_setting("tier_limit_1", str(val))
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
    builder.button(
        text="Отмена",
        callback_data="adm_rates_menu",
        icon_custom_emoji_id="5778527486270770928",
    )
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
        await update_setting("tier_limit_2", str(val))
        await state.clear()
        await show_admin_menu(message, state)
    except ValueError:
        await edit_or_reply(message, "Введите число:", state=state)


@router.callback_query(F.data == "adm_export_users")
async def adm_export_users(callback: CallbackQuery):
    if callback.from_user.id != int(ADMIN_ID):
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id, username, balance, total_deals FROM users")

    file_content = (
        f"{'USER_ID':<15} | {'USERNAME':<20} | {'BALANCE':<12} | {'DEALS':<6}\n"
    )
    file_content += "-" * 63 + "\n"
    for row in users:
        uname_str = f"@{row['username']}" if row['username'] else "none"
        file_content += (
            f"{str(row['user_id']):<15} | {uname_str:<20} | {f'{row[\"balance\"]} USDT':<12} |"
            f" {str(row['total_deals']):<6}\n"
        )

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
        await callback.answer("Недостаточно прав!", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        logs = await conn.fetch("SELECT id, user_id, username, action, created_at FROM system_logs ORDER BY id DESC")

    file_content = (
        f"{'ID':<6} | {'USER_ID':<15} | {'USERNAME':<18} | {'ACTION':<35} |"
        f" {'TIME':<19}\n"
    )
    file_content += "-" * 105 + "\n"
    for row in logs:
        uname_str = f"@{row['username']}" if row['username'] else "none"
        file_content += (
            f"{f'#{row[\"id\"]}':<6} | {str(row['user_id']):<15} | {uname_str:<18} |"
            f" {str(row['action']):<35} | {str(row['created_at']):<19}\n"
        )

        filename = "system_logs_export.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(file_content)

    await callback.message.answer_document(
        document=FSInputFile(filename), caption="Табличные системные логи:"
    )
    await callback.answer()


async def main():
    await init_db()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())