import re
import logging
from datetime import datetime, timedelta
from telegram import (
    Update,
    InputFile,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from config import TOKEN
from db import init_db, add_transaction, get_transactions, last_transactions
from openpyxl import Workbook
import os
import socket
import requests

logger = logging.getLogger(__name__)

BTN_REPORT = "📊 Отчёт"
BTN_REPORT_3_DAYS = "📅 3 дня"
BTN_REPORT_DEBTS = "📒 Долги 10"
BTN_REPORT_INCOME = "💰 Доходы 10"
BTN_EXPORT = "📥 Экспорт Excel"



def setup_logging():
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    log_file = "logs.txt"

    handlers = [logging.StreamHandler()]
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(
            logging.FileHandler(log_file, encoding="utf-8")
        )

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers
    )

    if log_level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.INFO)


# --------------------
# Парсинг сообщения
# --------------------

import re


def normalize_number(number_str: str) -> float:
    # Убираем пробелы, запятые и подчёркивания
    clean = re.sub(r"[ ,_]", "", number_str)
    return float(clean)


def parse_message(text: str):
    text = text.strip()

    # ---- Доход ----
    if text.startswith("+"):
        match = re.match(r"\+([\d\s,_]+)\s*(.*)", text)
        if match:
            amount = normalize_number(match.group(1))
            return "income", amount, match.group(2), None

    # ---- Долг ----
    if text.startswith("%"):
        match = re.match(r"%([\d\s,_]+)\s*(.*)", text)
        if match:
            amount = normalize_number(match.group(1))
            return "debt", amount, "", match.group(2)

    # ---- Расход ----
    match = re.match(r"^([\d\s,_]+)\s*(.*)", text)
    if match:
        amount = normalize_number(match.group(1))
        return "expense", amount, match.group(2), None

    return None# --------------------
# Клавиатура
# --------------------

def main_keyboard():
    keyboard = [
        [KeyboardButton(BTN_REPORT)],
        [KeyboardButton(BTN_REPORT_3_DAYS), KeyboardButton(BTN_REPORT_DEBTS), KeyboardButton(BTN_REPORT_INCOME)],
        [KeyboardButton(BTN_EXPORT)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --------------------
# Команда /start
# --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот учёта финансов запущен.\n\n"
        "Примеры:\n"
        "27800 магазин\n"
        "%64000 Жахонгир\n"
        "+72000 зарплата\n\n"
        "Для отчёта за период:\n"
        "/report 2026-03-01 2026-03-31",
        reply_markup=main_keyboard()
    )


# --------------------
# Обработчик текста
# --------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info("Message received: user_id=%s", update.effective_user.id)

    if text == BTN_REPORT:
        logger.info("Report requested via keyboard: user_id=%s", update.effective_user.id)
        return await report(update, context)

    if text == BTN_REPORT_3_DAYS:
        logger.info("Report 3 days requested via keyboard: user_id=%s", update.effective_user.id)
        return await report_last_days(update, context)

    if text == BTN_REPORT_DEBTS:
        logger.info("Debt report requested via keyboard: user_id=%s", update.effective_user.id)
        return await report_debts(update, context)

    if text == BTN_REPORT_INCOME:
        logger.info("Income report requested via keyboard: user_id=%s", update.effective_user.id)
        return await report_income(update, context)

    if text == BTN_EXPORT:
        logger.info("Excel export requested via keyboard: user_id=%s", update.effective_user.id)
        return await export_excel(update, context)

    result = parse_message(text)

    if not result:
        logger.warning("Invalid message format: user_id=%s text=%r", update.effective_user.id, text[:120])
        await update.message.reply_text("Неверный формат сообщения.")
        return

    t_type, amount, description, person = result

    add_transaction(
        user_id=update.effective_user.id,
        t_type=t_type,
        amount=amount,
        description=description,
        person=person
    )
    logger.info("Transaction saved: user_id=%s type=%s amount=%s", update.effective_user.id, t_type, amount)
    if t_type == "income":
        tx_type = "Доход"
    elif t_type == "expense":
        tx_type = "Расход"
    elif t_type == "debt":
        tx_type = "Долг"

    await update.message.reply_text(
        f"✅ Сохранено: {tx_type} | {amount}",
        reply_markup=main_keyboard()
    )


def build_full_report_text(transactions, title):
    total_income = 0
    total_expense = 0
    total_debt = 0

    text = f"{title}\n\n"

    for t in transactions:
        t_type, amount, desc, person, created = t

        if t_type == "income":
            total_income += amount
            tx_type = "Доход"
        elif t_type == "expense":
            total_expense += amount
            tx_type = "Расход"
        elif t_type == "debt":
            total_debt += amount
            tx_type = "Долг"

        text += f"{created[:10]} | {tx_type} | {amount} | {desc or person}\n"

    text += "\n------\n"
    text += f"Доходы: {total_income}\n"
    text += f"Расходы: {total_expense}\n"
    text += f"Долги: {total_debt}\n"

    return text


def build_single_type_text(transactions, title, total_label):
    total = 0

    text = f"{title}\n\n"

    for t in transactions:
        _t_type, amount, desc, person, created = t
        total += amount
        text += f"{created[:10]} | {amount} | {desc or person}\n"

    text += "\n------\n"
    text += f"{total_label}: {total}\n"

    return text


async def report_last_days(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int = 3):
    user_id = update.effective_user.id
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    logger.info(
        "Report last days requested: user_id=%s days=%s start=%s end=%s",
        user_id,
        days,
        start_date,
        end_date
    )

    transactions = last_transactions(
        user_id,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=10
    )

    if not transactions:
        logger.info("No transactions for last days report: user_id=%s", user_id)
        await update.message.reply_text("Нет данных за последние 3 дня.")
        return

    text = build_full_report_text(transactions, f"📅 Отчёт за {days} дня:")
    await update.message.reply_text(text)


async def report_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info("Debt report requested: user_id=%s", user_id)
    transactions = last_transactions(user_id, t_type="debt", limit=10)

    if not transactions:
        logger.info("No debt transactions for report: user_id=%s", user_id)
        await update.message.reply_text("Нет записей по долгам.")
        return

    text = build_single_type_text(transactions, "📒 Долги (последние 10):", "Итого долги")
    await update.message.reply_text(text)


async def report_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info("Income report requested: user_id=%s", user_id)
    transactions = last_transactions(user_id, t_type="income", limit=10)

    if not transactions:
        logger.info("No income transactions for report: user_id=%s", user_id)
        await update.message.reply_text("Нет записей по доходам.")
        return

    text = build_single_type_text(transactions, "💰 Доходы (последние 10):", "Итого доходы")
    await update.message.reply_text(text)


# --------------------
# Отчёт с периодом
# --------------------

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    start_date = None
    end_date = None

    # Если вызвано через команду /report
    if context.args:
        try:
            start_date = context.args[0]
            end_date = context.args[1]

            # Проверка формата даты
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")

        except:
            logger.warning("Invalid report date format: user_id=%s args=%s", user_id, context.args)
            await update.message.reply_text(
                "Формат даты: /report 2026-03-01 2026-03-31"
            )
            return

    logger.info("Report requested: user_id=%s start=%s end=%s", user_id, start_date, end_date)
    transactions = last_transactions(
        user_id,
        start_date=start_date,
        end_date=end_date,
        limit = 10
    )

    if not transactions:
        logger.info("No transactions for report: user_id=%s start=%s end=%s", user_id, start_date, end_date)
        await update.message.reply_text("Нет данных за выбранный период.")
        return

    text = build_full_report_text(transactions, "📊 Отчёт:")
    await update.message.reply_text(text)


# --------------------
# Экспорт
# --------------------

async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    transactions = get_transactions(user_id)

    if not transactions:
        logger.info("No transactions to export: user_id=%s", user_id)
        await update.message.reply_text("Нет данных для экспорта.")
        return

    logger.info("Export requested: user_id=%s count=%s", user_id, len(transactions))
    wb = Workbook()
    ws = wb.active
    ws.append(["Тип", "Сумма", "Описание", "Человек", "Дата"])

    for row in transactions:
        ws.append(row)
    file_name = f"report_{user_id}.xlsx"

    wb.save(file_name)

    logger.info("Export file created: %s", file_name)


    await update.message.reply_document(
        document=file_name
    )

    os.remove(file_name)
    logger.info("Export file removed: %s", file_name)

async def ipaddress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception as e:
        local_ip = f"Ошибка получения локального IP: {e}"

    try:
        response = requests.get('https://api.ipify.org', timeout=5)
        global_ip = response.text.strip()
    except Exception as e:
        global_ip = f"Ошибка получения глобального IP: {e}"

    await update.message.reply_text(f"Локальный IP: {local_ip}\nГлобальный IP: {global_ip}")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    update_id = getattr(update, "update_id", None)
    exc = context.error
    logger.error(
        "Unhandled error while processing update_id=%s",
        update_id,
        exc_info=(type(exc), exc, exc.__traceback__)
    )


# --------------------
# Main
# --------------------

def main():
    setup_logging()
    logger.info("Bot starting...")
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("ipaddress", ipaddress))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
