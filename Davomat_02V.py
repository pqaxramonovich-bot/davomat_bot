import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from aiohttp import web


# =========================================================
# SOZLAMALAR (Render Environment Variables dan o'qiladi)
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8977586369:AAHr-eQDJncP7SOSEbp3lhGA9FeAo8ahiTk")
PORT = int(os.getenv("PORT", "10000"))

ADMIN_IDS = {
    1111917826,
}

DB_NAME = "davomat.db"


# =========================================================
# GURUHLAR (Tyutor: Ismoilova Salimabonu)
# =========================================================

GROUPS = [
    "12/25 Bt",
    "14/25 MS",
    "16/25 OOT",
    "17/25 OOT",
    "19/25 OOT (rus)",
    "20/25 O'HK",
    "21/25 QXMT",
    "15/24 TM",
    "17/24 TM (rus)",
    "18/24 Log",
    "20/24 MMXT",
    "2-24",
    "11-24",
]


# =========================================================
# LOG
# =========================================================

logging.basicConfig(level=logging.INFO)


# =========================================================
# DATABASE
# =========================================================

conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    group_name TEXT NOT NULL,
    date TEXT NOT NULL,
    total_students INTEGER NOT NULL,
    absent_count INTEGER NOT NULL,
    present_count INTEGER NOT NULL,
    absent_names TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()


# =========================================================
# BOT
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

user_sessions = {}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_group(index):
    try:
        return GROUPS[int(index)]
    except:
        return None


def groups_keyboard():
    buttons = []
    for i, group in enumerate(GROUPS):
        buttons.append(
            InlineKeyboardButton(text=group, callback_data=f"group:{i}")
        )
    rows = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i + 2])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton(text="👥 Guruhni tanlash", callback_data="choose_group")]
    ]
    if is_admin(user_id):
        buttons.append([
            InlineKeyboardButton(text="📊 Statistika", callback_data="statistics"),
            InlineKeyboardButton(text="📥 Excel olish", callback_data="excel")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 <b>Davomat botiga xush kelibsiz!</b>\n\n"
        "📚 Guruhingizni tanlash uchun quyidagi tugmani bosing.",
        reply_markup=main_keyboard(message.from_user.id)
    )


@dp.callback_query(F.data == "choose_group")
async def choose_group(callback: CallbackQuery):
    await callback.message.edit_text(
        "👥 <b>Guruhingizni tanlang:</b>",
        reply_markup=groups_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("group:"))
async def group_selected(callback: CallbackQuery):
    index = callback.data.split(":")[1]
    group = get_group(index)
    if not group:
        await callback.answer("Guruh topilmadi!", show_alert=True)
        return

    today = datetime.now().strftime("%Y-%m-%d")

    existing = cursor.execute(
        "SELECT id FROM attendance WHERE group_name = ? AND date = ?",
        (group, today)
    ).fetchone()

    if existing:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Guruhlar", callback_data="choose_group")]]
        )
        await callback.message.edit_text(
            f"👥 <b>{group}</b>\n\n📅 Sana: <b>{today}</b>\n\n"
            "⚠️ Bu guruh uchun bugungi davomat allaqachon kiritilgan.",
            reply_markup=keyboard
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Davomatni boshlash", callback_data=f"start:{index}")],
            [InlineKeyboardButton(text="⬅️ Guruhlar", callback_data="choose_group")]
        ]
    )
    await callback.message.edit_text(
        f"👥 <b>{group}</b>\n\nDavomatni boshlash uchun quyidagi tugmani bosing.",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("start:"))
async def start_attendance(callback: CallbackQuery):
    index = callback.data.split(":")[1]
    group = get_group(index)
    user_sessions[callback.from_user.id] = {
        "group": group,
        "total": None,
        "absent": None,
        "absent_names": []
    }
    await show_total_count(callback)


async def show_total_count(callback):
    keyboard = number_keyboard(prefix="total", include_zero=False)
    await callback.message.edit_text(
        f"📝 <b>Davomatni boshlash</b>\n\n"
        f"👥 Guruh: <b>{user_sessions[callback.from_user.id]['group']}</b>\n\n"
        "🔢 Guruhdagi <b>jami talabalar sonini</b> tanlang:",
        reply_markup=keyboard
    )
    await callback.answer()


def number_keyboard(max_number=30, include_zero=False, prefix="num"):
    buttons = []
    start = 0 if include_zero else 1
    for i in range(start, max_number + 1, 5):
        row = []
        for j in range(i, min(i + 5, max_number + 1)):
            row.append(InlineKeyboardButton(text=str(j), callback_data=f"{prefix}:{j}"))
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.callback_query(F.data.startswith("total:"))
async def total_selected(callback: CallbackQuery):
    number = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Sessiya tugagan. /start ni bosing.", show_alert=True)
        return

    user_sessions[user_id]["total"] = number
    group = user_sessions[user_id]["group"]

    keyboard = number_keyboard(max_number=number, prefix="absent", include_zero=True)
    await callback.message.edit_text(
        f"👥 Guruh: <b>{group}</b>\n\n👨‍🎓 Jami talabalar: <b>{number}</b> ta\n\n"
        "❌ Endi <b>kelmagan talabalar sonini</b> tanlang (0 bo'lishi ham mumkin):",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("absent:"))
async def absent_selected(callback: CallbackQuery):
    number = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Sessiya tugagan.", show_alert=True)
        return

    total = user_sessions[user_id]["total"]
    if number > total:
        await callback.answer("❌ Kelmaganlar soni jami talabalar sonidan ko‘p bo‘lishi mumkin emas!", show_alert=True)
        return

    user_sessions[user_id]["absent"] = number
    group = user_sessions[user_id]["group"]

    if number == 0:
        user_sessions[user_id]["absent_names"] = []
        await show_confirmation(callback)
        return

    await callback.message.edit_text(
        f"👥 Guruh: <b>{group}</b>\n\n👨‍🎓 Jami: <b>{total}</b> ta\n❌ Kelmaganlar: <b>{number}</b> ta\n\n"
        f"✍️ Endi <b>{number} ta</b> kelmagan talabaning ism-familiyasini yozib yuboring.\n\n"
        "<b>Masalan:</b>\n<code>Aliyev A</code>\n<code>Valiyeva M</code>\n\n"
        "Har bir ism-familiya yangi qatorda bo‘lsin.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"group:{GROUPS.index(group)}")
        ]])
    )
    user_sessions[user_id]["waiting_names"] = True
    await callback.answer()


@dp.message()
async def receive_names(message: Message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]
    if not session.get("waiting_names", False):
        return

    text = message.text.strip()
    if not text:
        await message.answer("⚠️ Ism-familiyalarni kiriting.")
        return

    names = [line.strip() for line in text.splitlines() if line.strip()]
    required = session["absent"]

    if len(names) != required:
        await message.answer(
            f"⚠️ Siz <b>{required} ta</b> kelmagan talaba kiritishingiz kerak.\n\n"
            f"Hozir <b>{len(names)} ta</b> ism kiritildi.\n\n"
            "Iltimos, qaytadan to‘g‘ri miqdorda ism-familiya yuboring."
        )
        return

    session["absent_names"] = names
    session["waiting_names"] = False
    await show_confirmation_message(message)


async def show_confirmation_message(message: Message):
    user_id = message.from_user.id
    session = user_sessions[user_id]
    group, total, absent, names = session["group"], session["total"], session["absent"], session["absent_names"]
    present = total - absent

    text = (
        "📋 <b>DAVOMAT MA'LUMOTLARI</b>\n\n"
        f"👥 Guruh: <b>{group}</b>\n\n"
        f"👨‍🎓 Jami: <b>{total}</b> ta\n"
        f"✅ Kelgan: <b>{present}</b> ta\n"
        f"❌ Kelmagan: <b>{absent}</b> ta\n\n"
        "<b>Kelmaganlar:</b>\n"
    )
    for i, name in enumerate(names, 1):
        text += f"{i}. {name}\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Davomatni saqlash", callback_data="save")],
            [InlineKeyboardButton(text="✏️ Qayta kiritish", callback_data="restart")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")]
        ]
    )
    await message.answer(text, reply_markup=keyboard)


async def show_confirmation(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = user_sessions[user_id]
    group, total, absent = session["group"], session["total"], session["absent"]
    present = total - absent

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Davomatni saqlash", callback_data="save")],
            [InlineKeyboardButton(text="✏️ Qayta kiritish", callback_data="restart")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")]
        ]
    )
    await callback.message.edit_text(
        "📋 <b>DAVOMAT MA'LUMOTLARI</b>\n\n"
        f"👥 Guruh: <b>{group}</b>\n\n"
        f"👨‍🎓 Jami: <b>{total}</b> ta\n"
        f"✅ Kelgan: <b>{present}</b> ta\n"
        f"❌ Kelmagan: <b>{absent}</b> ta\n\n"
        "ℹ️ Kelmaganlar soni 0 bo‘lgani uchun ism-familiya kiritilmadi.",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data == "restart")
async def restart(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Sessiya topilmadi.", show_alert=True)
        return
    user_sessions[user_id]["total"] = None
    user_sessions[user_id]["absent"] = None
    user_sessions[user_id]["absent_names"] = []
    user_sessions[user_id]["waiting_names"] = False
    await show_total_count(callback)


@dp.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery):
    user_sessions.pop(callback.from_user.id, None)
    await callback.message.edit_text(
        "❌ <b>Davomat kiritish bekor qilindi.</b>\n\nQaytadan boshlash uchun guruhni tanlang.",
        reply_markup=main_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "save")
async def save_attendance(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Sessiya topilmadi.", show_alert=True)
        return

    session = user_sessions[user_id]
    group, total, absent, names = session["group"], session["total"], session["absent"], session["absent_names"]
    present = total - absent
    today = datetime.now().strftime("%Y-%m-%d")

    existing = cursor.execute(
        "SELECT id FROM attendance WHERE group_name = ? AND date = ?",
        (group, today)
    ).fetchone()

    if existing:
        await callback.answer("Bu guruh uchun bugungi davomat allaqachon saqlangan!", show_alert=True)
        return

    absent_text = ", ".join(names) if names else "-"

    cursor.execute(
        """
        INSERT INTO attendance
        (user_id, group_name, date, total_students, absent_count, present_count, absent_names)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, group, today, total, absent, present, absent_text)
    )
    conn.commit()
    user_sessions.pop(user_id, None)

    await callback.message.edit_text(
        "✅ <b>DAVOMAT SAQLANDI!</b>\n\n"
        f"👥 Guruh: <b>{group}</b>\n📅 Sana: <b>{today}</b>\n\n"
        f"👨‍🎓 Jami talabalar: <b>{total}</b> ta\n"
        f"✅ Kelganlar: <b>{present}</b> ta\n"
        f"❌ Kelmaganlar: <b>{absent}</b> ta",
        reply_markup=main_keyboard(user_id)
    )
    await callback.answer("Davomat saqlandi!")


@dp.callback_query(F.data == "statistics")
async def statistics(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo‘q!", show_alert=True)
        return

    rows = cursor.execute(
        """
        SELECT group_name, COUNT(*) as days, SUM(total_students), SUM(present_count), SUM(absent_count)
        FROM attendance GROUP BY group_name ORDER BY group_name
        """
    ).fetchall()

    text = "📊 <b>DAVOMAT STATISTIKASI</b>\n\n"
    if not rows:
        text += "⚠️ Hozircha davomat ma'lumotlari mavjud emas."
    else:
        for row in rows:
            text += f"👥 <b>{row[0]}</b>\n📅 Kunlar: {row[1]} ta\n👨‍🎓 Jami: {row[2]}\n✅ Kelgan: {row[3]}\n❌ Kelmagan: {row[4]}\n\n"

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Asosiy menyu", callback_data="main")]]
        )
    )
    await callback.answer()


# =========================================================
# EXCEL YARATISH
# =========================================================

async def create_excel(chat_id):
    wb = Workbook()
    ws = wb.active
    ws.title = "Davomat"

    current_date = datetime.now().strftime("%d.%m.%Y-yil")

    thin_border = Border(
        left=Side(style='thin', color='000000'),
        right=Side(style='thin', color='000000'),
        top=Side(style='thin', color='000000'),
        bottom=Side(style='thin', color='000000')
    )

    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"Guruhlar kesimida talabalar to‘g‘risida MA’LUMOT    Ismoilova Salimabonu    {current_date}"
    title_cell.font = Font(bold=True, size=11)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    
    for col in range(1, 7):
        ws.cell(row=1, column=col).border = thin_border

    headers = [
        "T/p",
        "Guruh",
        "Jami talabalar soni",
        "Bugun kelgan talabalar soni",
        "Jami foizda",
        "Kelmagan talabalar"
    ]
    ws.append([])
    ws.append(headers)

    header_font = Font(bold=True, size=10)
    for col in range(1, 7):
        cell = ws.cell(row=3, column=col)
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    rows = cursor.execute(
        """
        SELECT group_name, total_students, present_count, absent_names
        FROM attendance
        WHERE date = date('now')
        ORDER BY group_name
        """
    ).fetchall()

    if not rows:
        latest_date = cursor.execute("SELECT MAX(date) FROM attendance").fetchone()
        if latest_date and latest_date[0]:
            rows = cursor.execute(
                """
                SELECT group_name, total_students, present_count, absent_names
                FROM attendance WHERE date = ?
                ORDER BY group_name
                """,
                (latest_date[0],)
            ).fetchall()

    total_all_students = 0
    total_all_present = 0

    current_row = 4
    for i, r in enumerate(GROUPS, 1):
        found = next((item for item in rows if item[0] == r), None)
        if found:
            g_name, t_num, p_num, names = found
            percentage = round((p_num / t_num) * 100, 2) if t_num > 0 else 0
            absent_str = names if names else "-"
            total_all_students += t_num
            total_all_present += p_num
        else:
            t_num, p_num, percentage, absent_str = 0, 0, 0, "-"

        row_data = [
            i,
            r,
            t_num,
            p_num,
            f"{percentage}%" if t_num > 0 else "0%",
            absent_str
        ]
        ws.append(row_data)

        for col in range(1, 7):
            c = ws.cell(row=current_row, column=col)
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = thin_border

        current_row += 1

    total_percentage = round((total_all_present / total_all_students) * 100, 2) if total_all_students > 0 else 0
    
    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=2)
    
    ws.cell(row=current_row, column=1, value="Жами")
    ws.cell(row=current_row, column=3, value=total_all_students)
    ws.cell(row=current_row, column=4, value=total_all_present)
    ws.cell(row=current_row, column=5, value=f"{total_percentage}%")
    ws.cell(row=current_row, column=6, value="-")

    for col in range(1, 7):
        c = ws.cell(row=current_row, column=col)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = thin_border

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 25
    ws.column_dimensions["E"].width = 15
    ws.column_dimensions["F"].width = 35

    file = BytesIO()
    wb.save(file)
    file.seek(0)

    document = BufferedInputFile(
        file.read(),
        filename=f"Davomat_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    )

    await bot.send_document(
        chat_id=chat_id,
        document=document,
        caption="📊 <b>Kunlik davomat tayyor\n\n Bot yaratuvchisi: @Pakhlavon_21</b>"
    )


@dp.callback_query(F.data == "excel")
async def excel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo‘q!", show_alert=True)
        return

    await callback.answer("📥 Excel tayyorlanmoqda...")
    await create_excel(callback.from_user.id)


@dp.callback_query(F.data == "main")
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏠 <b>Asosiy menyu</b>\n\nKerakli bo‘limni tanlang:",
        reply_markup=main_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizda admin huquqi mavjud emas.")
        return
    await message.answer(
        "⚙️ <b>ADMIN PANEL</b>\n\nKerakli bo‘limni tanlang:",
        reply_markup=main_keyboard(message.from_user.id)
    )


# =========================================================
# WEB SERVER (UptimeRobot uchun aiohttp)
# =========================================================

async def handle(request):
    return web.Response(text="Davomat Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Web server started on port {PORT}")


# =========================================================
# MAIN (Bot va Web Serverni birgalikda ishga tushirish)
# =========================================================

async def main():
    print("=" * 50)
    print("DAVOMAT BOT ISHGA TUSHMOQDA")
    print("=" * 50)
    
    # Bot va Web serverni parallel ishga tushiramiz
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")
    finally:
        conn.close()