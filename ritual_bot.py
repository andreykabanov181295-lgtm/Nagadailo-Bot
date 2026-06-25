#!/usr/bin/env python3
"""
Telegram Ritual Reminder Bot — два кроки
Нагадує випити таблетки та нанести спрей для волосся.
Ескалує блатний тон з кожним пропущеним нагадуванням.
"""

import logging
from datetime import time
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

import os
BOT_TOKEN = os.environ.get("BOT_TOKEN")    # Отримай у @BotFather

REMINDER_HOUR   = 8    # Година першого нагадування
REMINDER_MINUTE = 0    # Хвилина першого нагадування
INTERVAL_MINUTES = 60  # Інтервал між повторними нагадуваннями

# ============================================================
# 💬  ТЕКСТИ — ЕСКАЛАЦІЯ ЗА КІЛЬКІСТЮ НАГАДУВАНЬ
# ============================================================

# Індекс = кількість вже надісланих нагадувань (0, 1, 2, 3+)
REMINDERS = [
    # 0 — перше, м'яке
    "Йо, братуха! 👋\n\nЧас для щоденного ритуалу:\n💊 Таблетки\n💈 Спрей для волосся\n\nЗроби та відміч нижче 👇",
    # 1 — друге, вже серйозніше
    "Чуєш, чебурек, ти шо мене не поняв? 😑\n\nТаблетки та спрей самі себе не зроблять.\nТикай кнопку як зробиш 👇",
    # 2 — третє, підвищений тон
    "Слухай, кабан, я вже вдруге кажу — шевелись! 🐗\n\nЩо незрозуміло? Таблетки. Спрей. Кнопка. Три дії.",
    # 3 — четверте, дуже незадоволений
    "ТРЕТІЙ РАЗ ПИШУ! ТРЕТІЙ! 🤌\n\nТи тут взагалі є, чи шо? Відгукнись, людино.\nТаблетки + спрей = свобода від моїх повідомлень.",
    # 4+ — максимальна ескалація
    "Дивись, я ввічливий, але ти мою ввічливість не цінуєш. 😤\n\nЯ не відстану — ти ж мене знаєш.\nТАБЛЕТКИ. СПРЕЙ. ВСЕ.",
]

LATE_REMINDERS = [
    "Слухай, я й сам хочу спати, але поки ти не натиснеш — не піду. 😴\n\n💊 Таблетки\n💈 Спрей\n\nОпівночі закриваємо касу. Устигай.",
    "Ти шо, вампір? Всі нормальні люди вже сплять, а ти досі не зробив ритуал. 🧛\n\n💊 Таблетки\n💈 Спрей\n\nДавай, я теж хочу відпочити.",
    "Північ скоро, Попелюшко. 🎃\n\nКарета не поїде поки не натиснеш кнопку.\n\n💊 Таблетки\n💈 Спрей",
    "Слухай, я не сплю через тебе вже який час. 😤\n\nОстанній раз питаю по-людськи:\n\n💊 Таблетки\n💈 Спрей",
]

# Підтвердження однієї дії
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

# Підтвердження всього ритуалу
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

# Стан користувачів: { chat_id: {"pills": bool, "spray": bool, "count": int} }
user_state: dict[int, dict] = {}


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

    # Пізній час — спеціальний текст
    if hour is not None and hour >= 22:
        return pick(LATE_REMINDERS, s["count"])

    # Ескалація
    idx = min(count, len(REMINDERS) - 1)
    base = REMINDERS[idx]

    # Якщо одна дія вже зроблена — уточнення
    if s["pills"] and not s["spray"]:
        base += "\n\n✅ Таблетки вже є. Залишився спрей 💈"
    elif s["spray"] and not s["pills"]:
        base += "\n\n✅ Спрей вже є. Залишились таблетки 💊"

    return base


def pick(lst: list, index: int) -> str:
    return lst[index % len(lst)]


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    if is_done(chat_id):
        return

    from datetime import datetime
    hour = datetime.now().hour

    s = get_state(chat_id)
    text = get_reminder_text(chat_id, hour)
    keyboard = get_keyboard(chat_id)

    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    s["count"] += 1
    logger.info(f"[{chat_id}] Нагадування #{s['count']} надіслано")


async def reset_daily(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    user_state[chat_id] = {"pills": False, "spray": False, "count": 0}
    logger.info(f"[{chat_id}] Стан скинуто на новий день")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    s = get_state(chat_id)
    data = query.data  # "done_pills" або "done_spray"

    if data == "done_pills":
        s["pills"] = True
        key = "pills"
    elif data == "done_spray":
        s["spray"] = True
        key = "spray"
    else:
        return

    if is_done(chat_id):
        # Обидві дії виконано
        text = pick(CONFIRM_ALL, s["count"])
        await query.edit_message_text(f"🎉 {text}")
        logger.info(f"[{chat_id}] Ритуал повністю виконано")
    else:
        # Одна дія виконана, інша залишилась
        text = pick(CONFIRM_ONE[key], s["count"])
        await query.edit_message_text(text, reply_markup=get_keyboard(chat_id))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {"pills": False, "spray": False, "count": 0}

    # Очищаємо старі задачі
    for suffix in ["", "_repeat", "_reset"]:
        for job in context.job_queue.get_jobs_by_name(f"{chat_id}{suffix}"):
            job.schedule_removal()

    # Щоденне перше нагадування
    context.job_queue.run_daily(
        send_reminder,
        time=time(REMINDER_HOUR, REMINDER_MINUTE),
        chat_id=chat_id,
        name=str(chat_id),
    )
    # Повторні нагадування
    context.job_queue.run_repeating(
        send_reminder,
        interval=INTERVAL_MINUTES * 60,
        first=INTERVAL_MINUTES * 60,
        chat_id=chat_id,
        name=f"{chat_id}_repeat",
    )
    # Скидання о 00:00
    context.job_queue.run_daily(
        reset_daily,
        time=time(0, 0),
        chat_id=chat_id,
        name=f"{chat_id}_reset",
    )

    await update.message.reply_text(
        f"✅ Бот запущено, братуха!\n\n"
        f"📅 Перше нагадування: щодня о {REMINDER_HOUR:02d}:{REMINDER_MINUTE:02d}\n"
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

    await update.message.reply_text(text, reply_markup=None if is_done(chat_id) else get_keyboard(chat_id))


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for suffix in ["", "_repeat", "_reset"]:
        for job in context.job_queue.get_jobs_by_name(f"{chat_id}{suffix}"):
            job.schedule_removal()
    await update.message.reply_text(
        "🛑 Ладно, відстаю. Але завтра повернусь.\nНапиши /start щоб запустити знову."
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^done_(pills|spray)$"))

    logger.info("Бот запущено...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
