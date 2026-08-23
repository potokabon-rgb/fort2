import asyncio
logging = None
import logging
import random
import sqlite3
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
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
TOKEN = "8919102783:AAFlB5ICuD7WzONLHzeW5dspJKj17TT7UMg"
ADMIN_ID = 8075312868

SUPPORT_USERNAME = "@Derzywork"
REQUIRED_CHANNEL = "@FortunaPayNews"
REVIEWS_GROUP_ID = -1003589211301
REVIEWS_GROUP_USERNAME = "@FortunaPayRep"
LOG_CHANNEL_ID = -1004443604049

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()


# --- БАЗА ДАННЫХ ---
def init_db():
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("""
                       CREATE TABLE IF NOT EXISTS settings
                       (
                           key
                           TEXT
                           PRIMARY
                           KEY,
                           value
                           TEXT
                       )""")

    cursor.execute("""
                       CREATE TABLE IF NOT EXISTS users
                       (
                           user_id
                           INTEGER
                           PRIMARY
                           KEY,
                           username
                           TEXT,
                           balance
                           REAL
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
                           INTEGER
                           DEFAULT
                           NULL,
                           joined_date
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )""")

    cursor.execute("""
                       CREATE TABLE IF NOT EXISTS orders
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           user_id
                           INTEGER,
                           amount_usdt
                           REAL,
                           amount_rub
                           REAL,
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
                           INTEGER
                           DEFAULT
                           NULL,
                           sent_rub
                           REAL
                           DEFAULT
                           0.0,
                           remainder_usdt
                           REAL
                           DEFAULT
                           0.0,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )""")

    cursor.execute("""
                       CREATE TABLE IF NOT EXISTS system_logs
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           user_id
                           INTEGER,
                           username
                           TEXT,
                           action
                           TEXT,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )""")

    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate_tier_1', '80.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate_tier_2', '90.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rate_tier_3', '120.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tier_limit_1', '6.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tier_limit_2', '20.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tier_limit_3', '80.0')")
    conn.commit()
  finally:
    conn.close()


init_db()


def get_setting(key: str) -> str:
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    res = cursor.fetchone()
    return res[0] if res else ""
  finally:
    conn.close()


def update_setting(key: str, value: str):
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
  finally:
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


async def edit_or_reply(event: Message | CallbackQuery, text: str, reply_markup=None, state: FSMContext = None):
  data = await state.get_data() if state else {}
  main_msg_id = data.get("main_msg_id")

  if isinstance(event, CallbackQuery):
    try:
      if main_msg_id and main_msg_id != event.message.message_id:
        try:
          await event.message.bot.delete_message(chat_id=event.message.chat.id, message_id=main_msg_id)
        except Exception:
          pass
      msg = await event.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown", disable_web_page_preview=True)
      if state:
        await state.update_data(main_msg_id=msg.message_id)
    except Exception:
      try:
        if main_msg_id:
          try:
            await event.message.bot.delete_message(chat_id=event.message.chat.id, message_id=main_msg_id)
          except Exception:
            pass
        msg = await event.message.answer(text, reply_markup=reply_markup, parse_mode="Markdown", disable_web_page_preview=True)
        if state:
          await state.update_data(main_msg_id=msg.message_id)
      except Exception as e:
        logging.error(f"Ошибка редактирования/отправки сообщения в Callback: {e}")
    await event.answer()
  else:
    if main_msg_id:
      try:
        await event.bot.delete_message(chat_id=event.chat.id, message_id=main_msg_id)
      except Exception:
        pass

    try:
      await event.delete()
    except Exception:
      pass

    try:
      new_msg = await event.answer(text, reply_markup=reply_markup, parse_mode="Markdown", disable_web_page_preview=True)
      if state:
        await state.update_data(main_msg_id=new_msg.message_id)
    except Exception as e:
      logging.error(f"Ошибка отправки сообщения в Message: {e}")


async def send_log(user_id: int, username: str, action: str):
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("INSERT INTO system_logs (user_id, username, action) VALUES (?, ?, ?)", (user_id, username, action))
    conn.commit()
  except Exception as e:
    logging.error(f"Ошибка записи лога в БД: {e}")
  finally:
    conn.close()

  if not LOG_CHANNEL_ID:
    return
  try:
    user_mention = f"@{username}" if username else f"ID: `{user_id}`"
    log_text = f"Лог системы Fortuna Pay\n\nПользователь: {user_mention}\nID: `{user_id}`\nДействие: {action}"
    await bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_text, parse_mode="Markdown")
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


async def check_subscription(user_id: int) -> bool:
  if not REQUIRED_CHANNEL:
    return True
  try:
    member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
    if isinstance(member, (ChatMemberOwner, ChatMemberAdministrator, ChatMemberMember)):
      if member.status not in ("left", "kicked"):
        return True
  except Exception as e:
    logging.error(f"Ошибка проверки подписки: {e}")
    return False
  return False


def sub_check_kb():
  builder = InlineKeyboardBuilder()
  if REQUIRED_CHANNEL:
    builder.button(text="Подписаться на канал", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}", icon_custom_emoji_id="5920090136627908485")
  builder.button(text="Проверить подписку", callback_data="check_sub", icon_custom_emoji_id="5920052658743283381")
  builder.adjust(1)
  return builder.as_markup()


def main_menu_kb():
  builder = InlineKeyboardBuilder()
  builder.button(text="Личный кабинет", callback_data="profile", icon_custom_emoji_id="5883964170268840032")
  builder.button(text="Продать USDT", callback_data="sell_usdt", icon_custom_emoji_id="5992430854909989581")
  builder.button(text="Калькулятор", callback_data="calculator", icon_custom_emoji_id="5935938364086685805")
  builder.button(text="Актуальные курсы", callback_data="exchange_rate", icon_custom_emoji_id="5994378914636500516")
  builder.button(text="Мои заявки", callback_data="history", icon_custom_emoji_id="5967456680940671207")
  builder.button(text="Рефералы", callback_data="referral_menu", icon_custom_emoji_id="5877530150345641603")
  builder.button(text="Отзывы", callback_data="reviews", icon_custom_emoji_id="5958376256788502078")
  builder.button(text="Поддержка", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}", icon_custom_emoji_id="5778575233422200567")
  builder.adjust(2, 2, 2, 2, 1)
  return builder.as_markup()


def menu_button_kb():
  builder = InlineKeyboardBuilder()
  builder.button(text="Главное меню", callback_data="main_menu", icon_custom_emoji_id="6008258140108231117")
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

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT user_id, referrer_id FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    if not exists:
      cursor.execute("INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)", (user_id, username, referrer_id))
    else:
      current_ref = exists[1]
      if not current_ref and referrer_id and referrer_id != user_id:
        cursor.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
      cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
  finally:
    conn.close()

  if not await check_subscription(user_id):
    text = f"[🔒](tg://emoji?id=5920090136627908485) **Требуется подписка**\n\nДля использования сервиса подпишитесь на официальный канал: `{REQUIRED_CHANNEL}`\n\nПосле подписки нажмите кнопку проверки ниже:"
    await edit_or_reply(event, text, reply_markup=sub_check_kb(), state=state)
    return

  if isinstance(event, Message):
    await send_log(user_id, username, "Запустил бота / Главное меню")

  menu_text = (
      f"[💎](tg://emoji?id=5994378914636500516) **Fortuna Pay** — Безопасный автоматизированный обмен [✨](tg://emoji?id=5992430854909989581)\n\n"
      f"[🪙](tg://emoji?id=5992430854909989581) О сервисе: Мы осуществляем моментальный обмен ваших USDT [🚀](tg://emoji?id=5935938364086685805)\n"
      f"[🛡](tg://emoji?id=5883964170268840032) • 100% гарантия безопасности сделок [🔒](tg://emoji?id=5883964170268840032)\n"
      f"[📈](tg://emoji?id=5931515758952583071) • Лучшие курсы рынка [🔥](tg://emoji?id=5994378914636500516)\n"
      f"[💬](tg://emoji?id=5778575233422200567) • Круглосуточная поддержка [⭐️](tg://emoji?id=5958376256788502078)\n\n"
      f"[👇](tg://emoji?id=5935938364086685805) Выберите нужный раздел в меню ниже:"
  )

  # ==========================================
  # 🖼️ ПОДСКАЗКА: ВСТАВКА ФОТОГРАФИИ ПО ССЫЛКЕ
  # ==========================================
  # Вставьте сюда вашу прямую ссылку на картинку (в конце должен быть .jpg, .jpeg или .png)
  photo_url = "https://github.com/potokabon-rgb/ffff/blob/main/fortik.jpg?raw=true"
  # ==========================================

  # Логика отправки главного меню с фото (удаляем старое сообщение и шлем картинку с кнопками)
  if isinstance(event, CallbackQuery):
    try:
      await event.message.delete()
    except Exception:
      pass
    try:
      msg = await event.message.answer_photo(photo=photo_url, caption=menu_text, reply_markup=main_menu_kb(), parse_mode="Markdown")
      if state:
        await state.update_data(main_msg_id=msg.message_id)
    except Exception as e:
      logging.error(f"Не удалось отправить фото в Callback: {e}")
      await edit_or_reply(event, menu_text, reply_markup=main_menu_kb(), state=state)
  else:
    try:
      await event.delete()
    except Exception:
      pass
    try:
      msg = await event.answer_photo(photo=photo_url, caption=menu_text, reply_markup=main_menu_kb(), parse_mode="Markdown")
      if state:
        await state.update_data(main_msg_id=msg.message_id)
    except Exception as e:
      logging.error(f"Не удалось отправить фото в Message: {e}")
      await edit_or_reply(event, menu_text, reply_markup=main_menu_kb(), state=state)


@router.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery, state: FSMContext):
  if await check_subscription(callback.from_user.id):
    # При возврате в меню здесь можно также вызвать cmd_start или оставить текстовый ответ
    await cmd_start(callback, state)
  else:
    await callback.answer("Вы всё еще не подписаны на канал!", show_alert=True)


@router.callback_query(F.data == "reviews")
async def reviews_handler(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
 [cite: 10] await send_log(user_id, callback.from_user.username, "Открыл отзывы")

  text = (
      "[⭐](tg://emoji?id=5958376256788502078) **Отзывы о сервисе Fortuna Pay** [💬](tg://emoji?id=5778575233422200567)\n\n"
      "Вы можете ознакомиться с реальными отзывами наших клиентов или оставить свой собственный отзыв сразу после завершения успешного обмена! [🔥](tg://emoji?id=5994378914636500516)"
  )

  builder = InlineKeyboardBuilder()
  if REVIEWS_GROUP_USERNAME:
    builder.button(text="Почитать отзывы в канале", url=f"https://t.me/{REVIEWS_GROUP_USERNAME.replace('@', '')}", icon_custom_emoji_id="5931628549088744687")
  builder.button(text="Главное меню", callback_data="main_menu", icon_custom_emoji_id="6008258140108231117")
  builder.adjust(1)

  await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "profile")
async def user_profile(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  username = callback.from_user.username
  await send_log(user_id, username, "Открыл профиль")

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT balance, total_deals, completed_deals, joined_date FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
  finally:
    conn.close()

  balance, total, completed, joined = res if res else (0.0, 0, 0, "Неизвестно")

  profile_text = (
      f"[👤](tg://emoji?id=5883964170268840032) **Личный кабинет** [✨](tg://emoji?id=5994378914636500516)\n\n"
      f"[🆔](tg://emoji?id=5994378914636500516) ID: `{user_id}`\n"
      f"[💬](tg://emoji?id=5778575233422200567) Юзернейм: @{username if username else 'отсутствует'}\n"
      f"[📅](tg://emoji?id=5967456680940671207) Регистрация: `{joined}`\n\n"
      f"[📊](tg://emoji?id=5931515758952583071) **Статистика сделок:** [📈](tg://emoji?id=5931515758952583071)\n"
      f"[🪙](tg://emoji?id=5992430854909989581) Баланс аккаунта: `{balance:.2f} USDT` [💎](tg://emoji?id=5994378914636500516)\n"
      f"[📁](tg://emoji?id=5935938364086685805) Всего заявок: `{total}` (Успешно: `{completed}`) [🔥](tg://emoji?id=5992430854909989581)"
  )

  await edit_or_reply(callback, profile_text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  bot_info = await bot.get_me()
  ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    ref_count = cursor.fetchone()[0]
  finally:
    conn.close()

  text = (
      f"[🎁](tg://emoji?id=5877530150345641603) **Реферальная система (3%)** [💎](tg://emoji?id=5994378914636500516)\n\n"
      f"Приглашайте друзей и получайте **3%** от суммы их успешных обменов прямо на ваш баланс! [🚀](tg://emoji?id=5935938364086685805)\n\n"
      f"[🔗](tg://emoji?id=5931515758952583071) **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
      f"[👥](tg://emoji?id=5883964170268840032) Приглашено пользователей: `{ref_count}` [🔥](tg://emoji?id=5992430854909989581)"
  )
  await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "calculator")
async def calculator_start(callback: CallbackQuery, state: FSMContext):
  await send_log(callback.from_user.id, callback.from_user.username, "Открыл калькулятор")
  r1 = get_setting("rate_tier_1")
  r2 = get_setting("rate_tier_2")
  r3 = get_setting("rate_tier_3")
  lim1 = get_setting("tier_limit_1")
  lim2 = get_setting("tier_limit_2")

  text = (
      "[🧮](tg://emoji?id=5935938364086685805) **Калькулятор USDT ➔ RUB** [📊](tg://emoji?id=5931515758952583071)\n\n"
      "Действующие тарифные ставки:\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • До {lim1} USDT ➔ `{r1} ₽`\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • От {lim1} до {lim2} USDT ➔ `{r2} ₽`\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • От {lim2} USDT ➔ `{r3} ₽`\n\n"
      "[💬](tg://emoji?id=5778575233422200567) Отправляйте числа сообщением — сумма будет пересчитываться автоматически:"
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
      f"[📈](tg://emoji?id=5931515758952583071) **Результат расчета:** [🪙](tg://emoji?id=5992430854909989581)\n\n"
      f"Сумма к обмену: `{amount} USDT`\n"
      f"Примененный курс: `{rate} ₽` / USDT\n"
      f"Вы получите: `{total_rub} ₽` [🔥](tg://emoji?id=5994378914636500516)\n\n"
      f"*Можете отправить другое число для мгновенного пересчета:*"
  )

  await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "sell_usdt")
async def sell_usdt_start(callback: CallbackQuery, state: FSMContext):
  await send_log(callback.from_user.id, callback.from_user.username, "Начал создание заявки на продажу")

  r1 = get_setting("rate_tier_1")
  r2 = get_setting("rate_tier_2")
  r3 = get_setting("rate_tier_3")
  lim1 = get_setting("tier_limit_1")
  lim2 = get_setting("tier_limit_2")

  text = (
      f"[💎](tg://emoji?id=5994378914636500516) **Создание заявки на обмен** [🚀](tg://emoji?id=5935938364086685805)\n\n"
      f"[📊](tg://emoji?id=5931515758952583071) Действующие курсы:\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • До {lim1}$ ➔ `{r1} ₽`\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • {lim1}-{lim2}$ ➔ `{r2} ₽`\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • От {lim2}$ ➔ `{r3} ₽`\n\n"
      f"[🪙](tg://emoji?id=5992430854909989581) Отправьте сообщением сумму USDT, которую хотите обменять:"
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
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    user_balance = res[0] if res else 0.0
  finally:
    conn.close()

  rate, _ = get_rate_for_amount(amount)
  total_rub = round(amount * rate, 2)

  await state.update_data(amount_usdt=amount, amount_rub=total_rub, user_balance=user_balance)

  if user_balance > 0:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Списать с баланса ({min(user_balance, amount):.2f} USDT)", callback_data="use_balance_yes", icon_custom_emoji_id="5778318458802409852")
    builder.button(text="Оплатить полностью через чек", callback_data="use_balance_no", icon_custom_emoji_id="5992430854909989581")
    builder.button(text="Главное меню", callback_data="main_menu", icon_custom_emoji_id="6008258140108231117")
    builder.adjust(1)

    text = (
        f"[🪙](tg://emoji?id=5992430854909989581) Обнаружен внутренний баланс: `{user_balance:.2f} USDT`\n\n"
        f"Желаете ли вы использовать средства с баланса для частичной или полной оплаты заявки на `{amount} USDT`?"
    )
    await edit_or_reply(message, text, reply_markup=builder.as_markup(), state=state)
    await state.set_state(SellStates.waiting_for_balance_choice)
  else:
    text = (
        f"Заявка: {amount} USDT (`{total_rub} ₽`)\n"
        f"Курс: `{rate} ₽` / USDT\n\n"
        f"Шаг 1 из 2: Отправьте ссылку на чек из @CryptoBot\n"
        f"*(Пример: `https://t.me/CryptoBot?start=...`)*:"
    )
    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_receipt)


@router.callback_query(F.data.in_({"use_balance_yes", "use_balance_no"}), StateFilter(SellStates.waiting_for_balance_choice))
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
    conn = sqlite3.connect("usdt_exchange.db")
    cursor = conn.cursor()
    try:
      cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount_usdt, user_id))
      cursor.execute(
          """
                       INSERT INTO orders (user_id, amount_usdt, amount_rub, check_link, status)
                       VALUES (?, ?, ?, 'Оплачено с баланса', 'Ожидает реквизиты')
                       """,
          (user_id, amount_usdt, amount_rub),
      )
      order_id = cursor.lastrowid
      cursor.execute("UPDATE users SET total_deals = total_deals + 1 WHERE user_id = ?", (user_id,))
      conn.commit()
    finally:
      conn.close()

    await state.update_data(order_id=order_id, check_link="Оплачено с баланса")

    text = (
        "Оплата с баланса успешна!\n\n"
        "Шаг 2 из 2: Укажите реквизиты для получения оплаты\n\n"
        "Отправьте сообщением данные:\n"
        "• Номер телефона / карты\n"
        "• Название банка\n"
        "• ФИО получателя\n\n"
        "*(Пример: `+79991234567, Т-Банк, Иванов Иван И.`)*"
    )
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_requisites)
  else:
    link_instruction = (
        f"С баланса списано `{used_from_balance:.2f} USDT`. Остаток нужно доплатить через чек."
        if used_from_balance > 0
        else "Отправьте ссылку на чек из `@CryptoBot`:"
    )
    text = f"Заявка: {amount_usdt} USDT (`{amount_rub} ₽`)\n\n{link_instruction}"
    await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)
    await state.set_state(SellStates.waiting_for_receipt)


@router.message(SellStates.waiting_for_receipt)
async def process_sell_receipt_link(message: Message, state: FSMContext):
  check_link = message.text.strip()
  if "t.me" not in check_link.lower() and "http" not in check_link.lower():
    text = "Некорректная ссылка на чек.\n\nПожалуйста, отправьте валидную ссылку из `@CryptoBot`\n*(Пример: `https://t.me/CryptoBot?start=...`)*:"
    await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
    return

  data = await state.get_data()
  amount_usdt = data.get("amount_usdt")
  amount_rub = data.get("amount_rub")
  used_from_balance = data.get("used_from_balance", 0.0)
  user_id = message.from_user.id

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    if used_from_balance > 0:
      cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (used_from_balance, user_id))

    cursor.execute(
        """
                       INSERT INTO orders (user_id, amount_usdt, amount_rub, check_link, status)
                       VALUES (?, ?, ?, ?, 'Ожидает реквизиты')
                       """,
        (user_id, amount_usdt, amount_rub, check_link),
    )
    order_id = cursor.lastrowid
    conn.commit()
  finally:
    conn.close()

  await state.update_data(order_id=order_id, check_link=check_link)

  text = (
      "Ссылка принята!\n\n"
      "Шаг 2 из 2: Укажите реквизиты для получения оплаты\n\n"
      "Отправьте сообщением данные:\n"
      "• Номер телефона / карты\n"
      "• Название банка\n"
      "• ФИО получателя\n\n"
      "*(Пример: `+79991234567, Т-Банк, Иванов Иван И.`)*"
  )
  await edit_or_reply(message, text, reply_markup=menu_button_kb(), state=state)
  await state.set_state(SellStates.waiting_for_requisites)


@router.message(SellStates.waiting_for_requisites)
async def process_sell_requisites(message: Message, state: FSMContext):
  raw_req = message.text.strip()

  if len(raw_req) < 5:
    text = "Слишком короткий текст. Укажите подробные реквизиты (Телефон, Банк, ФИО):"
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

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute(
        """
                       UPDATE orders
                       SET phone  = ?,
                           bank   = ?,
                           fio    = ?,
                           status = 'Ожидает администратора'
                       WHERE id = ?
                       """,
        (phone, bank, fio, order_id),
    )

    cursor.execute("UPDATE users SET total_deals = total_deals + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
  finally:
    conn.close()

  await send_log(user_id, username, f"Создал заявку #{order_id} на сумму {amount_usdt} USDT")

  balance_note = f"\nСписано с баланса: `{used_from_balance:.2f} USDT`" if used_from_balance > 0 else ""
  success_text = (
      f"Заявка #{order_id} полностью сформирована!\n\n"
      f"Сумма: `{amount_usdt} USDT` (`{amount_rub} ₽`){balance_note}\n"
      f"Реквизиты: `{raw_req}`\n\n"
      f"Статус: **Ожидает обработку администратором...**"
  )
  await edit_or_reply(message, success_text, reply_markup=main_menu_kb(), state=state)

  builder = InlineKeyboardBuilder()
  builder.button(text="Взять заявку", callback_data=f"take_order_{order_id}", icon_custom_emoji_id="5906995262378741881")

  admin_text = (
      f"🔔 **НОВАЯ ЗАЯВКА #{order_id} ГОТОВА К ОБРАБОТКЕ!**\n\n"
      f"Пользователь: @{username} (`{user_id}`)\n"
      f"Сумма: `{amount_usdt} USDT` (`{amount_rub} ₽`){balance_note}\n"
      f"Реквизиты: `{raw_req}`\n"
      f"Чек: {check_link}"
  )

  try:
    await message.bot.send_message(chat_id=int(ADMIN_ID), text=admin_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
  except Exception as e:
    logging.error(f"Не удалось отправить уведомление админу: {e}")

  await state.clear()


@router.callback_query(F.data.startswith("take_order_"))
async def take_order_handler(callback: CallbackQuery):
  if callback.from_user.id != int(ADMIN_ID):
    await callback.answer("Вы не администратор!", show_alert=True)
    return

  order_id = int(callback.data.split("_")[-1])
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT status, user_id FROM orders WHERE id = ?", (order_id,))
    res = cursor.fetchone()

    if not res:
      await callback.answer("Заявка не найдена в базе.", show_alert=True)
      return

    status, client_id = res
    if status not in ("Ожидает администратора", "Ожидает реквизиты"):
      await callback.answer(f"Заявка уже обработана или находится в статусе: {status}", show_alert=True)
      return

    cursor.execute("UPDATE orders SET status = 'В работе', admin_id = ? WHERE id = ?", (callback.from_user.id, order_id))
    conn.commit()
  finally:
    conn.close()

  builder = InlineKeyboardBuilder()
  builder.button(text="Ввести отправленную сумму", callback_data=f"pay_order_{order_id}", icon_custom_emoji_id="5994297722574737553")

  try:
    await callback.message.edit_text(text=callback.message.text + f"\n\nВ работе у: @{callback.from_user.username}", reply_markup=builder.as_markup(), parse_mode="Markdown")
  except Exception:
    pass

  await callback.answer(f"Заявка #{order_id} взята в работу!")

  try:
    await bot.send_message(chat_id=client_id, text=f"Ваша заявка #{order_id} взята в обработку администратором! Идет проверка чека и выплата.", parse_mode="Markdown")
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
  await state.update_data(order_id=order_id, main_msg_id=data.get("main_msg_id"))

  builder = InlineKeyboardBuilder()
  builder.button(text="Отмена", callback_data="adm_menu", icon_custom_emoji_id="5778527486270770928")

  await edit_or_reply(callback, f"Введите фактически переведенную сумму в рублях (`RUB`) для заявки **#{order_id}**:", reply_markup=builder.as_markup(), state=state)


@router.message(AdminStates.waiting_for_payout_amount)
async def process_admin_payout_amount(message: Message, state: FSMContext):
  if message.from_user.id != int(ADMIN_ID):
    return

  try:
    sent_rub = float(message.text.strip().replace(",", "."))
    if sent_rub < 0:
      raise ValueError
  except ValueError:
    await edit_or_reply(message, "Ошибка ввода. Введите корректную сумму числом (например, `1500`):", state=state)
    return

  data = await state.get_data()
  order_id = data.get("order_id")

  if not order_id:
    await edit_or_reply(message, "Сессия обработки заказа не найдена.", reply_markup=menu_button_kb(), state=state)
    await state.clear()
    return

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT user_id, amount_rub, amount_usdt FROM orders WHERE id = ?", (order_id,))
    res = cursor.fetchone()

    if not res:
      await edit_or_reply(message, "Заявка не найдена.", reply_markup=menu_button_kb(), state=state)
      await state.clear()
      return

    client_id, expected_rub, amount_usdt = res

    if sent_rub < expected_rub:
      remainder_rub = round(expected_rub - sent_rub, 2)
      rate, _ = get_rate_for_amount(amount_usdt)
      remainder_usdt = round(remainder_rub / rate, 2)

      cursor.execute("UPDATE orders SET sent_rub = ?, remainder_usdt = ?, status = 'Ожидает решения по остатку' WHERE id = ?", (sent_rub, remainder_usdt, order_id))
      conn.commit()

      builder = InlineKeyboardBuilder()
      builder.button(text="Зачислить остаток на баланс ($)", callback_data=f"usr_rem_balance_{order_id}", icon_custom_emoji_id="5769403330761593044")
      builder.button(text="Оставить на чай", callback_data=f"usr_rem_tip_{order_id}", icon_custom_emoji_id="5899833370052923106")
      builder.adjust(1)

      user_text = (
          f"Выплата по заявке #{order_id} частичная!\n\n"
          f"Переведено: `{sent_rub} ₽` из `{expected_rub} ₽`\n"
          f"Недоплата составила: `{remainder_rub} ₽` (≈ `{remainder_usdt} USDT`)\n\n"
          f"Укажите, как поступить с остатком средств:"
      )

      try:
        await bot.send_message(chat_id=client_id, text=user_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await edit_or_reply(message, f"Перевод зафиксирован частично (`{sent_rub} ₽`). Запрос решений отправлен клиенту #{client_id}.", state=state)
      except Exception as e:
        logging.error(f"Ошибка уведомления клиента: {e}")
    else:
      cursor.execute("UPDATE orders SET sent_rub = ?, status = 'Ожидает подтверждения' WHERE id = ?", (sent_rub, order_id))
      conn.commit()

      await finalize_payout(bot, client_id, sent_rub, order_id)
      await edit_or_reply(message, f"Выплата по заявке #{order_id} на сумму {sent_rub} ₽ проведена.", state=state)
  finally:
    conn.close()

  await state.clear()


@router.callback_query(F.data.startswith("usr_rem_balance_") | F.data.startswith("usr_rem_tip_"))
async def process_user_remainder_choice(callback: CallbackQuery, state: FSMContext):
  action = "balance" if "usr_rem_balance_" in callback.data else "tip"
  order_id = int(callback.data.split("_")[-1])
  user_id = callback.from_user.id

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT remainder_usdt, sent_rub FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
    res = cursor.fetchone()

    if not res:
      await callback.answer("Заявка не найдена.", show_alert=True)
      return

    remainder_usdt, sent_rub = res

    if action == "balance":
      cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (remainder_usdt, user_id))
      choice_text = f"Остаток `{remainder_usdt:.2f} USDT` успешно зачислен на ваш внутренний баланс!"
    else:
      cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('total_tips_usdt', '0')")
      cursor.execute("UPDATE settings SET value = CAST(value AS REAL) + ? WHERE key = 'total_tips_usdt'", (remainder_usdt,))
      choice_text = "Большое спасибо! Остаток передан в качестве чаевых."

    cursor.execute("UPDATE orders SET status = 'Ожидает подтверждения' WHERE id = ?", (order_id,))
    conn.commit()
  finally:
    conn.close()

  await edit_or_reply(callback, f"Ваш выбор принят.\n\n{choice_text}", state=state)
  await finalize_payout(bot, user_id, sent_rub, order_id, extra_text=choice_text)


async def finalize_payout(bot_instance: Bot, client_id: int, sent_rub: float, order_id: int, extra_text: str = ""):
  builder = InlineKeyboardBuilder()
  builder.button(text="Деньги пришли", callback_data=f"confirm_yes_{order_id}", icon_custom_emoji_id="5776375003280838798")
  builder.button(text="Деньги не пришли", callback_data=f"confirm_no_{order_id}", icon_custom_emoji_id="5778527486270770928")
  builder.adjust(2)

  extra_block = f"{extra_text}\n" if extra_text else ""
  text = f"Выплата по заявке #{order_id} отправлена!\n\nСумма перевода: `{sent_rub}` ₽\n{extra_block}\nПожалуйста, проверьте баланс карты и подтвердите получение:"

  try:
    await bot_instance.send_message(chat_id=client_id, text=text, reply_markup=builder.as_markup(), parse_mode="Markdown")
  except Exception as e:
    logging.error(f"Не удалось отправить статус клиенту: {e}")


@router.callback_query(F.data.startswith("confirm_yes_"))
async def confirm_yes_handler(callback: CallbackQuery, state: FSMContext):
  order_id = int(callback.data.split("_")[-1])
  user_id = callback.from_user.id

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT status, amount_usdt FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
    res = cursor.fetchone()

    if not res:
      await callback.answer("Заявка не найдена.", show_alert=True)
      return

    status, amount_usdt = res
    if status == "Завершено":
      await callback.answer("Сделка уже подтверждена ранее.", show_alert=True)
      return

    cursor.execute("UPDATE orders SET status = 'Завершено' WHERE id = ?", (order_id,))
    cursor.execute("UPDATE users SET completed_deals = completed_deals + 1 WHERE user_id = ?", (user_id,))

    cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    ref_res = cursor.fetchone()
    if ref_res and ref_res[0]:
      referrer_id = ref_res[0]
      bonus = round(amount_usdt * 0.03, 4)
      cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, referrer_id))
      try:
        await bot.send_message(chat_id=referrer_id, text=f"Реферальный бонус!\nПользователь по вашей ссылке успешно завершил обмен. Вам начислено `{bonus} USDT` (3%).", parse_mode="Markdown")
      except Exception:
        pass

    conn.commit()
  finally:
    conn.close()

 [cite: 10] await send_log(user_id, callback.from_user.username, f"Успешно закрыл сделку #{order_id}")

  data = await state.get_data()
  await state.set_state(ReviewStates.waiting_for_review_text)
  await state.update_data(order_id=order_id, main_msg_id=data.get("main_msg_id"))

  builder = InlineKeyboardBuilder()
  builder.button(text="Пропустить отзыв", callback_data="skip_review", icon_custom_emoji_id="5771511103141975115")

  await edit_or_reply(callback, f"Сделка #{order_id} успешно завершена!\n\nНапишите короткий отзыв о работе сервиса Fortuna Pay ниже:", reply_markup=builder.as_markup(), state=state)

  try:
    await bot.send_message(chat_id=int(ADMIN_ID), text=f"Пользователь подтвердил получение средств по заявке #{order_id}. Сделка закрыта!", parse_mode="Markdown")
  except Exception:
    pass


@router.callback_query(F.data == "skip_review")
async def skip_review_handler(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  await edit_or_reply(callback, "Спасибо за обмен! Будем рады сотрудничать снова.", reply_markup=main_menu_kb(), state=state)


@router.message(ReviewStates.waiting_for_review_text)
async def process_user_review(message: Message, state: FSMContext):
  review_text = message.text.strip()
  user = message.from_user
  user_id = user.id
  username = user.username
  user_mention = f"@{username}" if username else f"ID: `{user_id}`"
  current_date = datetime.now().strftime("%d.%m.%Y %H:%M")

  formatted_review = f"Новый отзыв о Fortuna Pay\n\nОт: {user_mention}\nДата: `{current_date}`\n\nКомментарий:\n{review_text}"

  if REVIEWS_GROUP_ID:
    try:
      await bot.send_message(chat_id=REVIEWS_GROUP_ID, text=formatted_review, parse_mode="Markdown")
    except Exception as e:
      logging.error(f"Не удалось отправить отзыв в группу: {e}")

 [cite: 10] await send_log(user_id, username, "Оставил отзыв")
  await state.clear()

  await edit_or_reply(message, "Спасибо за ваш отзыв! Он передан в публичный канал отзывов.", reply_markup=main_menu_kb(), state=state)


@router.callback_query(F.data.startswith("confirm_no_"))
async def confirm_no_handler(callback: CallbackQuery, state: FSMContext):
  order_id = int(callback.data.split("_")[-1])
  user_id = callback.from_user.id

 [cite: 10] await send_log(user_id, callback.from_user.username, f"Сообщил о проблеме с выплатой по заявке #{order_id}")
  random_code = random.randint(1000, 9999)

  builder = InlineKeyboardBuilder()
  builder.button(text="Написать поддержке", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}", icon_custom_emoji_id="5778575233422200567")
  builder.button(text="Главное меню", callback_data="main_menu", icon_custom_emoji_id="6008258140108231117")
  builder.adjust(1)

  instruction_text = (
      f"Фиксация проблемы по заявке #{order_id}\n\n"
      f"Для решения диспута запишите видео экрана:\n\n"
      f"1. Откройте мобильное приложение банка\n"
      f"2. Покажите привязанный номер СБП\n"
      f"3. Пролистайте историю операций за сегодня\n"
      f"4. Откройте чек любой последней операции\n"
      f"5. Напишите код `{random_code}` в любом поле ввода\n\n"
      f"Отправьте запись администратору поддержки."
  )

  await edit_or_reply(callback, instruction_text, reply_markup=builder.as_markup(), state=state)

  try:
    await bot.send_message(chat_id=int(ADMIN_ID), text=f"ВНИМАНИЕ! Диспут по заявке #{order_id}. Клиент указал, что деньги не пришли (Код проверки: {random_code})", parse_mode="Markdown")
  except Exception:
    pass


@router.callback_query(F.data == "exchange_rate")
async def exchange_rate_handler(callback: CallbackQuery, state: FSMContext):
 [cite: 10] await send_log(callback.from_user.id, callback.from_user.username, "Посмотрел курс")
  r1 = get_setting("rate_tier_1")
  r2 = get_setting("rate_tier_2")
  r3 = get_setting("rate_tier_3")
  lim1 = get_setting("tier_limit_1")
  lim2 = get_setting("tier_limit_2")

  text = (
      f"[📊](tg://emoji?id=5931515758952583071) **Актуальные курсы обмена** [🪙](tg://emoji?id=5992430854909989581)\n\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • До {lim1} USDT ➔ `{r1} ₽` за 1 USDT\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • От {lim1} до {lim2} USDT ➔ `{r2} ₽` за 1 USDT\n"
      f"[🔹](tg://emoji?id=5883964170268840032) • От {lim2} USDT ➔ `{r3} ₽` за 1 USDT\n\n"
      f"[ℹ️](tg://emoji?id=5935938364086685805) Расчет курса пересчитывается автоматически."
  )
  await edit_or_reply(callback, text, reply_markup=menu_button_kb(), state=state)


@router.callback_query(F.data == "history")
async def history_handler(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
 [cite: 10] await send_log(user_id, callback.from_user.username, "Просмотр истории")

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status = 'Завершено' THEN 1 ELSE 0 END) FROM orders WHERE user_id = ?", (user_id,))
    total_q, completed_q = cursor.fetchone()
    total_q = total_q or 0
    completed_q = completed_q or 0

    cursor.execute("SELECT id, amount_usdt, amount_rub, status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    orders = cursor.fetchall()
  finally:
    conn.close()

  text = f"[📁](tg://emoji?id=5935938364086685805) **История ваших операций** [📊](tg://emoji?id=5931515758952583071)\n\nВсего заявок: `{total_q}` | Завершено: `{completed_q}`\n\nПоследние действия:"

  builder = InlineKeyboardBuilder()
  if orders:
    for o_id, a_usdt, a_rub, status in orders:
      builder.button(text=f"#{o_id} | {a_usdt} USDT ({status})", callback_data=f"view_order_{o_id}", icon_custom_emoji_id="5992430854909989581")

  builder.button(text="Главное меню", callback_data="main_menu", icon_custom_emoji_id="6008258140108231117")
  builder.adjust(1)

  await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data.startswith("view_order_"))
async def view_order_details(callback: CallbackQuery, state: FSMContext):
  o_id = int(callback.data.split("_")[-1])
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT amount_usdt, amount_rub, status, check_link, phone, bank, fio, created_at FROM orders WHERE id = ? AND user_id = ?", (o_id, callback.from_user.id))
    res = cursor.fetchone()
  finally:
    conn.close()

  if not res:
    await callback.answer("Заявка не найдена.", show_alert=True)
    return

  usdt, rub, status, link, phone, bank, fio, created = res
  text = f"Детали заявки #{o_id}\n\nСумма: `{usdt} USDT`\nОжидается к выплате: `{rub} ₽`\nТелефон: `{phone}`\nБанк: `{bank}`\nФИО: `{fio}`\nТекущий статус: `{status}`\nЧек: {link}\nВремя создания: `{created}`"

  builder = InlineKeyboardBuilder()
  builder.button(text="К истории", callback_data="history", icon_custom_emoji_id="5956561916573782596")
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

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('Ожидает администратора', 'Ожидает реквизиты')")
    pending_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('В работе', 'Ожидает решения по остатку', 'Ожидает подтверждения')")
    in_progress_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'Завершено'")
    completed_count = cursor.fetchone()[0]

    cursor.execute("SELECT value FROM settings WHERE key = 'total_tips_usdt'")
    tip_res = cursor.fetchone()
    total_tips = float(tip_res[0]) if tip_res else 0.0
  finally:
    conn.close()

  r1 = get_setting("rate_tier_1")
  r2 = get_setting("rate_tier_2")
  r3 = get_setting("rate_tier_3")
  lim1 = get_setting("tier_limit_1")
  lim2 = get_setting("tier_limit_2")

  text = (
      f"Панель управления сервисом Fortuna Pay\n\n"
      f"Всего пользователей: `{users_count}`\n"
      f"Новые заявки: `{pending_count}`\n"
      f"Активные заявки в работе: `{in_progress_count}`\n"
      f"Успешно завершено сделок: `{completed_count}`\n"
      f"💰 Всего оставили на чай: `{total_tips:.2f} USDT`\n\n"
      f"Текущие курсы и лимиты:\n"
      f"• До {lim1}$ ➔ `{r1} ₽`\n"
      f"• {lim1}-{lim2}$ ➔ `{r2} ₽`\n"
      f"• От {lim2}$ ➔ `{r3} ₽`"
  )

  builder = InlineKeyboardBuilder()
  builder.button(text=f"Ожидают ({pending_count})", callback_data="adm_pending_orders", icon_custom_emoji_id="5942640218170461901")
  builder.button(text=f"В работе ({in_progress_count})", callback_data="adm_in_progress_orders", icon_custom_emoji_id="5943042214224465443")
  builder.button(text="Завершенные сделки", callback_data="adm_completed_orders", icon_custom_emoji_id="5933613451044720529")
  builder.button(text="Изменить баланс юзера", callback_data="adm_edit_balance_start", icon_custom_emoji_id="5992430854909989581")
  builder.button(text="Изменить курсы/лимиты", callback_data="adm_rates_menu", icon_custom_emoji_id="5931515758952583071")
  builder.button(text="Рассылка", callback_data="adm_broadcast", icon_custom_emoji_id="5771695636411847302")
  builder.button(text="Выгрузить юзеров (TXT)", callback_data="adm_export_users", icon_custom_emoji_id="5908808657700655253")
  builder.button(text="Выгрузить логи (TXT)", callback_data="adm_export_system_logs", icon_custom_emoji_id="6017174676898321263")
  builder.button(text="Выход в меню", callback_data="main_menu", icon_custom_emoji_id="6008258140108231117")
  builder.adjust(2, 1, 1, 2, 2, 1)

  await edit_or_reply(event, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_menu")
async def adm_menu_cb(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    return
  await show_admin_menu(callback, state)


# --- УПРАВЛЕНИЕ БАЛАНСОМ ПОЛЬЗОВАТЕЛЯ АДМИНИСТРАТОРОМ ---
@router.callback_query(F.data == "adm_edit_balance_start")
async def adm_edit_balance_start(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    return
  builder = InlineKeyboardBuilder()
  builder.button(text="Отмена", callback_data="adm_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Введите **Telegram ID** пользователя, баланс которого хотите изменить:", reply_markup=builder.as_markup(), state=state)
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

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT balance, username FROM users WHERE user_id = ?", (target_id,))
    res = cursor.fetchone()
  finally:
    conn.close()

  if not res:
    await message.answer(f"Пользователь с ID `{target_id}` не найден в базе данных.", parse_mode="Markdown")
    return

  current_balance, uname = res
  await state.update_data(target_id=target_id)
  builder = InlineKeyboardBuilder()
  builder.button(text="Отмена", callback_data="adm_menu", icon_custom_emoji_id="5778527486270770928")

  await edit_or_reply(
      message,
      f"Пользователь: @{uname or 'отсутствует'} (`{target_id}`)\n"
      f"Текущий баланс: `{current_balance:.2f} USDT`\n\n"
      f"Введите новое значение баланса (число, например `15.5` или `0`):",
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

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, target_id))
    conn.commit()
  finally:
    conn.close()

  await state.clear()
  await message.answer(f"Баланс пользователя `{target_id}` успешно изменен на `{new_balance:.2f} USDT`!", parse_mode="Markdown")

  try:
    await bot.send_message(chat_id=target_id, text=f"Администратор обновил ваш баланс. Текущий баланс: `{new_balance:.2f} USDT`", parse_mode="Markdown")
  except Exception:
    pass

  await show_admin_menu(message, state)


@router.callback_query(F.data == "adm_rates_menu")
async def adm_rates_menu(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    return
  builder = InlineKeyboardBuilder()
  builder.button(text="Курс (1)", callback_data="adm_set_rate_1", icon_custom_emoji_id="5931515758952583071")
  builder.button(text="Курс (2)", callback_data="adm_set_rate_2", icon_custom_emoji_id="5931515758952583071")
  builder.button(text="Курс (3)", callback_data="adm_set_rate_3", icon_custom_emoji_id="5931515758952583071")
  builder.button(text="Лимит 1", callback_data="adm_set_limit_1", icon_custom_emoji_id="5924720918826848520")
  builder.button(text="Лимит 2", callback_data="adm_set_limit_2", icon_custom_emoji_id="5924720918826848520")
  builder.button(text="Назад", callback_data="adm_menu", icon_custom_emoji_id="5778527486270770928")
  builder.adjust(3, 2, 1)
  await edit_or_reply(callback, "Управление курсами и диапазонами:", reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_pending_orders")
async def adm_pending_orders(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    await callback.answer("Недостаточно прав!", show_alert=True)
    return

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("""
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
    orders = cursor.fetchall()
  finally:
    conn.close()

  if not orders:
    await callback.answer("Нет нераспределенных заявок.", show_alert=True)
    return

  builder = InlineKeyboardBuilder()
  text = "Необработанные заявки:\n\n"
  for o_id, u_id, usdt, rub, phone, bank, fio, status, check_link in orders:
    req_info = f"📞 `{phone}` | 🏦 `{bank}` | 👤 `{fio}`" if phone else "*Реквизиты еще не введены*"
    text += f"🆔 **#{o_id}** [{status}] | `{usdt} USDT` (`{rub} ₽`)\n🔗 Чек: {check_link}\n{req_info}\n\n"
    builder.button(text=f"Взять #{o_id}", callback_data=f"take_order_{o_id}", icon_custom_emoji_id="5906995262378741881")

  builder.button(text="Панель управления", callback_data="adm_menu", icon_custom_emoji_id="5775887550262546277")
  builder.adjust(1)

  await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_in_progress_orders")
async def adm_in_progress_orders(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    await callback.answer("Недостаточно прав!", show_alert=True)
    return

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("""
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
    orders = cursor.fetchall()
  finally:
    conn.close()

  if not orders:
    await callback.answer("Нет активных процессов.", show_alert=True)
    return

  builder = InlineKeyboardBuilder()
  text = "Заявки в обработке:\n\n"
  for o_id, u_id, usdt, rub, phone, bank, fio, status in orders:
    text += f"🆔 **#{o_id}** [{status}] | `{usdt} USDT` (`{rub} ₽`)\n📞 `{phone}` | 🏦 `{bank}` | 👤 `{fio}`\n\n"
    builder.button(text=f"Перевод по #{o_id}", callback_data=f"pay_order_{o_id}", icon_custom_emoji_id="5897958754267174109")

  builder.button(text="Панель управления", callback_data="adm_menu", icon_custom_emoji_id="5775887550262546277")
  builder.adjust(1)

  await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_completed_orders")
async def adm_completed_orders(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    await callback.answer("Недостаточно прав!", show_alert=True)
    return

  conn = sqlite3.connect("usdt_exchange.db")
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
    conn.close()

  if not orders:
    await callback.answer("Завершенных сделок пока нет.", show_alert=True)
    return

  text = "История последних выполненных сделок:\n\n"
  for o_id, u_id, usdt, rub, sent_rub in orders:
    text += f"🆔 **#{o_id}** | ID Клиента: `{u_id}` | `{usdt} USDT` ➔ `{sent_rub or rub} ₽`\n"

  builder = InlineKeyboardBuilder()
  builder.button(text="Панель управления", callback_data="adm_menu", icon_custom_emoji_id="5775887550262546277")

  await edit_or_reply(callback, text, reply_markup=builder.as_markup(), state=state)


@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    return
  data = await state.get_data()
  await state.update_data(main_msg_id=data.get("main_msg_id"))
  builder = InlineKeyboardBuilder()
  builder.button(text="Отмена", callback_data="adm_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Отправьте текст для рассылки всем пользователям:", reply_markup=builder.as_markup(), state=state)
  await state.set_state(AdminStates.waiting_for_broadcast)


@router.message(AdminStates.waiting_for_broadcast)
async def adm_broadcast_process(message: Message, state: FSMContext):
  if message.from_user.id != int(ADMIN_ID):
    return
  text = message.text
  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
  finally:
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

  await message.answer(f"Рассылка завершена!\nУспешно: `{success}`\nНе удалось: `{failed}`")
  await state.clear()
  await show_admin_menu(message, state)


@router.callback_query(F.data == "adm_set_rate_1")
async def adm_set_rate_1_start(callback: CallbackQuery, state: FSMContext):
  if callback.from_user.id != int(ADMIN_ID):
    return
  data = await state.get_data()
  await state.update_data(main_msg_id=data.get("main_msg_id"))
  builder = InlineKeyboardBuilder()
  builder.button(text="Отмена", callback_data="adm_rates_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Введите новый курс для Tier 1:", reply_markup=builder.as_markup(), state=state)
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
  builder.button(text="Отмена", callback_data="adm_rates_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Введите новый курс для Tier 2:", reply_markup=builder.as_markup(), state=state)
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
  builder.button(text="Отмена", callback_data="adm_rates_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Введите новый курс для Tier 3:", reply_markup=builder.as_markup(), state=state)
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
  builder.button(text="Отмена", callback_data="adm_rates_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Введите верхнюю границу для Tier 1 (например, `6.0`):", reply_markup=builder.as_markup(), state=state)
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
  builder.button(text="Отмена", callback_data="adm_rates_menu", icon_custom_emoji_id="5778527486270770928")
  await edit_or_reply(callback, "Введите верхнюю границу для Tier 2 (например, `20.0`):", reply_markup=builder.as_markup(), state=state)
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

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT user_id, username, balance, total_deals FROM users")
    users = cursor.fetchall()
  finally:
    conn.close()

  file_content = f"{'USER_ID':<15} | {'USERNAME':<20} | {'BALANCE':<12} | {'DEALS':<6}\n"
  file_content += "-" * 63 + "\n"
  for uid, uname, bal, deals in users:
    uname_str = f"@{uname}" if uname else "none"
    file_content += f"{str(uid):<15} | {uname_str:<20} | {f'{bal} USDT':<12} | {str(deals):<6}\n"

  filename = "users_export.txt"
  with open(filename, "w", encoding="utf-8") as f:
    f.write(file_content)

  await callback.message.answer_document(document=FSInputFile(filename), caption="Табличный список пользователей системы:")
  await callback.answer()


@router.callback_query(F.data == "adm_export_system_logs")
async def adm_export_system_logs(callback: CallbackQuery):
  if callback.from_user.id != int(ADMIN_ID):
    await callback.answer("Недостаточно прав!", show_alert=True)
    return

  conn = sqlite3.connect("usdt_exchange.db")
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT id, user_id, username, action, created_at FROM system_logs ORDER BY id DESC")
    logs = cursor.fetchall()
  finally:
    conn.close()

  file_content = f"{'ID':<6} | {'USER_ID':<15} | {'USERNAME':<18} | {'ACTION':<35} | {'TIME':<19}\n"
  file_content += "-" * 105 + "\n"
  for l_id, uid, uname, action, created in logs:
    uname_str = f"@{uname}" if uname else "none"
    file_content += f"{f'#{l_id}':<6} | {str(uid):<15} | {uname_str:<18} | {str(action):<35} | {str(created):<19}\n"

  filename = "system_logs_export.txt"
  with open(filename, "w", encoding="utf-8") as f:
    f.write(file_content)

  await callback.message.answer_document(document=FSInputFile(filename), caption="Табличные системные логи:")
  await callback.answer()


async def main():
  dp.include_router(router)
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())