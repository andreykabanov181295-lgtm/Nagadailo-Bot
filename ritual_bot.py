#!/usr/bin/env python3
"""
Telegram Ritual Reminder Bot — два кроки
Нагадує випити таблетки та нанести спрей для волосся.
Ескалує блатний тон з кожним пропущеним нагадуванням.
"""

import logging
import random
import json
import os
from datetime import time, datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ============================================================
# ⚙️  НАЛАШТУВАННЯ
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

REMINDER_HOUR    = 6     # 6 UTC = 8 за Римом (UTC+2)
REMINDER_MINUTE  = 0
INTERVAL_MINUTES = 60

STATE_FILE = "/tmp/bot_state.json"

# ============================================================
# 💬  ТЕКСТИ
# ============================================================

REMINDERS = [
    "Йо, братуха! 👋\n\nЧас для щоденного ритуалу:\n💊 Таблетки\n💈 Спрей для волосся\n\nЗроби та відміч нижче 👇",
    "Чуєш, чебурек, ти шо мене не поняв? 😑\n\nТаблетки та спрей самі себе не зроблять.\nТикай кнопку як зробиш 👇",
    "Слухай, кабан, я вже вдруге кажу — шевелись! 🐗\n\nЩо незрозуміло? Таблетки. Спрей. Кнопка. Три дії.",
    "ТРЕТІЙ РАЗ ПИШУ! ТРЕТІЙ! 🤌\n\nТи тут взагалі є, чи шо? Відгукнись, людино.\nТаблетки + спрей = свобода від моїх повідомлень.",
    "Дивись, я ввічливий, але ти мою ввічливість не цінуєш. 😤\n\nЯ не відстану — ти ж мене знаєш.\nТАБЛЕТКИ. СПРЕЙ. ВСЕ.",
]

LATE_REMINDERS = [
    "Слухай, я й сам хочу спати, але поки ти не натиснеш — не піду. 😴\n\n💊 Таблетки\n💈 Спрей\n\nОпівночі закриваємо касу. Устигай.",
    "Ти шо, вампір? Всі нормальні люди вже сплять, а ти досі не зробив ритуал. 🧛\n\n💊 Таблетки\n💈 Спрей\n\nДавай, я теж хочу відпочити.",
    "Північ скоро, Попелюшко. 🎃\n\nКарета не поїде поки не натиснеш кнопку.\n\n💊 Таблетки\n💈 Спрей",
    "Слухай, я не сплю через тебе вже який час. 😤\n\nОстанній раз питаю по-людськи:\n\n💊 Таблетки\n💈 Спрей",
]

CONFIRM_ONE = {
    "pills": [
        "Таблетки — зачот. 💊 Тепер спрей, не розслабляйся.",
        "Добре, одна справа є. Спрей залишився — давай.",
        "Норм. Половина діла зроблена. Спрей чекає.",
    ],
    "spray": [
        "Спрей — ок. 💈 Тепер таблетки, не забудь.",
        "Волосся щасливе. Але таблетки самі не вип'ються.",
        "Добре. Спрей є, таблетки чекають — доробляй.",
    ],
}

CONFIRM_ALL = [
    "О, живий! Все зроблено, молодець. Уважаю. 💪\nЗавтра знову перевірю, не розслабляйся.",
    "Ну нарєшті. Думав, ти там помер. Красава! 🎉\nМожеш іти гуляти — заслужив.",
    "Зачот. Ось так і живемо. Завтра знову прийду. 😎",
    "Прийнято. Я тебе люблю, але завтра знову буду тут. ❤️",
]

# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

user_state: dict[int, dict] = {}

# ============================================================
# 💾  ЗБЕРЕЖЕННЯ СТАНУ
# ============================================================

def save_state():
    try:
        serializable = {str(k): v for k, v in user_state.items()}
        with open(STATE_FILE, "w") as f:
            json.dump(serializable, f)
    except Exception as e:
        logger.error(f"Помилка збереження стану: {e}")


def load_state():
    global user_state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                user_state = {int(k): v for k, v in data.items()}
                logger.info(f"Стан завантажено: {len(user_state)} юзерів")
    except Exception as e:
        logger.error(f"Помилка завантаження стану: {e}")

# ============================================================
# 🔧  ДОПОМІЖНІ ФУНКЦІЇ
# ============================================================

def get_rome_hour() -> int:
    """Повертає поточну годину за Римом (UTC+2)."""
    rome_time = datetime.now(timezone(timedelta(hours=2)))
    return rome_time.hour


def get_state(chat_id: int) -> dict:
    if chat_id not in user_state:
        user_state[chat_id] = {"pills": False, "spray": False, "count": 0}
    return user_state[chat_id]


def is_done(chat_id: int) -> bool:
    s = get_state(chat_id)
    return s["pills"] and s["spray"]


def get_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    s = get_state(chat_id)
    buttons = []
    if not s["pills"]:
        buttons.append(InlineKeyboardButton("💊 Таблетки — зроблено", callback_data="done_pills"))
    if not s["spray"]:
        buttons.append(InlineKeyboardButton("💈 Спрей — нанесено", callback_data="done_spray"))
    return InlineKeyboardMarkup([[b] for b in buttons])


def get_reminder_text(chat_id: int, hour: int = None) -> str:
    s = get_state(chat_id)
    count = s["count"]

    if hour is not None and hour >= 22:
        base = random.choice(LATE_REMINDERS)
    elif count >= len(REMINDERS):
        base = random.choice(REMINDERS[2:])
    else:
        base = REMINDERS[count]

    if s["pills"] and not s["spray"]:
        base += "\n\n✅ Таблетки вже є. Залишився спрей 💈"
    elif s["spray"] and not s["pills"]:
        base += "\n\n✅ Спрей вже є. Залишились таблетки 💊"

    return base


def pick(lst: list, index: int) -> str:
    return lst[index % len(lst)]


def register_jobs(context, chat_id: int):
    """Реєструє всі задачі для юзера."""
    for suffix in ["", "_repeat", "_reset"]:
        for job in context.job_queue.get_jobs_by_name(f"{chat_id}{suffix}"):
            job.schedule_removal()

    # Перше нагадування щодня о 6:00 UTC = 8:00 за Римом
    context.job_queue.run_daily(
        send_reminder,
        time=time(REMINDER_HOUR, REMINDER_MINUTE),
        chat_id=chat_id,
        name=str(chat_id),
    )
    # Повторні нагадування кожну годину починаючи з 9:00 UTC = 11:00 за Римом
    # (тобто через годину після першого)
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 1, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat2",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 2, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat3",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 3, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat4",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 4, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat5",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 5, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat6",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 6, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat7",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 7, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat8",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 8, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat9",
    )
    context.job_queue.run_daily(
        send_repeating_reminder,
        time=time(REMINDER_HOUR + 9, REMINDER_MINUTE),
        chat_id=chat_id,
        name=f"{chat_id}_repeat10",
    )
    # Скидання о 00:00 UTC
    context.job_queue.run_daily(
        reset_daily,
        time=time(0, 0),
        chat_id=chat_id,
        name=f"{chat_id}_reset",
    )

# ============================================================
# 📨  НАГАДУВАННЯ
# ============================================================

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if is_done(chat_id):
        return
    hour = get_rome_hour()
    s = get_state(chat_id)
    text = get_reminder_text(chat_id, hour)
    keyboard = get_keyboard(chat_id)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    s["count"] += 1
    save_state()
    logger.info(f"[{chat_id}] Нагадування #{s['count']} надіслано")


async def send_repeating_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Повторне нагадування — надсилає тільки якщо не виконано."""
    chat_id = context.job.chat_id
    if is_done(chat_id):
        return
    hour = get_rome_hour()
    s = get_state(chat_id)
    text = get_reminder_text(chat_id, hour)
    keyboard = get_keyboard(chat_id)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    s["count"] += 1
    save_state()
    logger.info(f"[{chat_id}] Повторне нагадування #{s['count']} надіслано")


async def reset_daily(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    user_state[chat_id] = {"pills": False, "spray": False, "count": 0}
    save_state()
    logger.info(f"[{chat_id}] Стан скинуто на новий день")

# ============================================================
# 🤖  ОБРОБНИКИ КОМАНД
# ============================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    s = get_state(chat_id)
    data = query.data

    if data == "done_pills":
        s["pills"] = True
        key = "pills"
    elif data == "done_spray":
        s["spray"] = True
        key = "spray"
    else:
        return

    save_state()

    if is_done(chat_id):
        text = pick(CONFIRM_ALL, s["count"])
        await query.edit_message_text(f"🎉 {text}")
        logger.info(f"[{chat_id}] Ритуал повністю виконано")
    else:
        text = pick(CONFIRM_ONE[key], s["count"])
        await query.edit_message_text(text, reply_markup=get_keyboard(chat_id))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {"pills": False, "spray": False, "count": 0}
    save_state()

    register_jobs(context, chat_id)

    await update.message.reply_text(
        f"✅ Бот запущено, братуха!\n\n"
        f"📅 Перше нагадування: щодня о 08:00 за Римом\n"
        f"🔁 Повтор: кожні {INTERVAL_MINUTES} хвилин\n\n"
        f"Щодня чекаю підтвердження двох дій:\n"
        f"💊 Таблетки\n"
        f"💈 Спрей для волосся\n\n"
        f"Команди:\n"
        f"/done — позначити всe виконано вручну\n"
        f"/status — перевірити статус сьогодні\n"
        f"/stop — зупинити бота"
    )


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = get_state(chat_id)
    s["pills"] = True
    s["spray"] = True
    save_state()
    await update.message.reply_text(
        "✅ Все відмічено як виконано!\nМожеш іти гуляти, заслужив 💪"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = get_state(chat_id)
    pills = "✅" if s["pills"] else "❌"
    spray = "✅" if s["spray"] else "❌"

    if is_done(chat_id):
        text = "🎉 Сьогодні все виконано, красава!"
    else:
        text = f"Статус на сьогодні:\n{pills} Таблетки\n{spray} Спрей"

    await update.message.reply_text(
        text,
        reply_markup=None if is_done(chat_id) else get_keyboard(chat_id)
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for suffix in ["", "_repeat2", "_repeat3", "_repeat4", "_repeat5",
                   "_repeat6", "_repeat7", "_repeat8", "_repeat9", "_repeat10", "_reset"]:
        for job in context.job_queue.get_jobs_by_name(f"{chat_id}{suffix}"):
            job.schedule_removal()
    await update.message.reply_text(
        "🛑 Ладно, відстаю. Але завтра повернусь.\nНапиши /start щоб запустити знову."
    )


async def post_init(application: Application):
    """Відновлює задачі для всіх юзерів після перезапуску."""
    load_state()
    for chat_id in user_state:
        try:
            register_jobs(application, chat_id)
            logger.info(f"[{chat_id}] Задачі відновлено після перезапуску")
        except Exception as e:
            logger.error(f"[{chat_id}] Помилка відновлення: {e}")

# ============================================================
# 🚀  ЗАПУСК
# ============================================================

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^done_(pills|spray)$"))

    logger.info("Бот запущено...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
