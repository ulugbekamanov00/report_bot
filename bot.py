import re
from datetime import datetime
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
        [KeyboardButton("📊 Отчёт")],
        [KeyboardButton("📥 Экспорт Excel")]
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

    if text == "📊 Отчёт":
        return await report(update, context)

    if text == "📥 Экспорт Excel":
        return await export_excel(update, context)

    result = parse_message(text)

    if not result:
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
    if t_type == "income":
        tx_type = 'Доход'
    elif t_type == "expense":
        tx_type = 'Расход'
    elif t_type == "debt":
        tx_type = 'Долг'

    await update.message.reply_text(
        f"✅ Сохранено: {tx_type} | {amount}",
        reply_markup=main_keyboard()
    )


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
            await update.message.reply_text(
                "Формат даты: /report 2026-03-01 2026-03-31"
            )
            return

    transactions = last_transactions(
        user_id,
        start_date=start_date,
        end_date=end_date,
        limit = 10
    )

    if not transactions:
        await update.message.reply_text("Нет данных за выбранный период.")
        return

    total_income = 0
    total_expense = 0
    total_debt = 0

    text = "📊 Отчёт:\n\n"

    for t in transactions:
        t_type, amount, desc, person, created = t

        if t_type == "income":
            total_income += amount
            tx_type = 'Доход'
        elif t_type == "expense":
            total_expense += amount
            tx_type = 'Расход'
        elif t_type == "debt":
            total_debt += amount
            tx_type = 'Долг'

        text += f"{created[:10]} | {tx_type} | {amount} | {desc or person}\n"


    text += "\n------\n"
    text += f"Доходы: {total_income}\n"
    text += f"Расходы: {total_expense}\n"
    text += f"Долги: {total_debt}\n"

    await update.message.reply_text(text)


# --------------------
# Экспорт
# --------------------

async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    transactions = get_transactions(user_id)

    if not transactions:
        await update.message.reply_text("Нет данных для экспорта.")
        return

    wb = Workbook()
    ws = wb.active
    ws.append(["Тип", "Сумма", "Описание", "Человек", "Дата"])

    for row in transactions:
        ws.append(row)
    file_name = f"report_{user_id}.xlsx"

    wb.save(file_name)


    await update.message.reply_document(
        document=file_name
    )

    os.remove(file_name)
# --------------------
# Main
# --------------------

def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()