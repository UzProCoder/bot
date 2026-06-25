import asyncio
import logging
import json
import os
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# Supabase kutubxonasini ulash
from supabase import create_client, Client

# ================= CONFIG (XAVFSIZ VARIANT) =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 1973341892))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

DB_FILE = "murojaatlar.json"        # Local zaxira fayli

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("gls_bot")

# Supabase mijozini ishga tushirish (Agar secrets kiritilgan bo'lsa)
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase moduli muvaffaqiyatli ulandi.")
else:
    logger.warning("Supabase URL yoki KEY topilmadi. Ma'lumotlar faqat JSON faylda saqlanadi!")

MFY_LIST = [
    "Boyovut", "Terakzor", "Oltin Vodiy", "Furqat", "Sharq Haqiqati",
    "Sohilobod", "Ibrat", "Dostlik", "Ahillik", "A.Yassaviy",
    "Beshbuloq", "Inoqlik", "Chortoq", "A.Navoiy", "Birlashgan",
    "Zarbdor", "Ishonch", "Baxmal", "Yulduz", "Mevazor",
    "Soyibobod", "Mustaqillik", "Tajribakor", "H.Olimjon",
]

CATEGORY = [
    ("Moddiy yordam", "cat1"),
    ("Nogironlik va TIEK", "cat2"),
    ("Reabilitatsiya", "cat3"),
    ("Sanatoriy", "cat4"),
    ("Vasiylik", "cat5"),
    ("Sayyor xizmatlar", "cat6"),
]
CATEGORY_NAMES = {code: name for name, code in CATEGORY}

SKIP_TEXT = "⏭ O'tkazish"
CONTACT_BUTTON_TEXT = "📱 Kontakt yuborish"
MFY_PER_PAGE = 6

# ================= JSON BAZA BILAN ISHLASH =================
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def generate_unique_id():
    db = load_db()
    while True:
        short_id = str(random.randint(1000, 9999))
        if short_id not in db:
            return short_id

# ================= STATES =================
class Form(StatesGroup):
    fio = State()
    mfy = State()
    category = State()
    contact = State()
    extra = State()
    text = State()

class AdminState(StatesGroup):
    waiting_for_reject_reason = State()

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= KEYBOARDS =================
def mfy_page_kb(page: int = 0) -> InlineKeyboardMarkup:
    start = page * MFY_PER_PAGE
    end = start + MFY_PER_PAGE
    items = MFY_LIST[start:end]
    kb = [[InlineKeyboardButton(text=m, callback_data=f"mfy|{i}")] for i, m in enumerate(items, start=start)]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page|{page - 1}"))
    if end < len(MFY_LIST):
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page|{page + 1}"))
    if nav:
        kb.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=name, callback_data=f"cat|{code}")] for name, code in CATEGORY])

def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=CONTACT_BUTTON_TEXT, request_contact=True)], [KeyboardButton(text=SKIP_TEXT)]], resize_keyboard=True, one_time_keyboard=True)

def admin_action_kb(appeal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"adm_accept|{appeal_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_reject|{appeal_id}")
        ],
        [InlineKeyboardButton(text="🏁 Tugatish (Hal etildi)", callback_data=f"adm_close|{appeal_id}")]
    ])

# ================= USER PROCESS =================
@dp.message(F.text == "/start")
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Assalomu alaykum! Murojaat qabul qilish botiga xush kiribsiz.\n\nF.I.SH kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.fio)

@dp.message(F.text == "/holat")
async def check_status(m: types.Message):
    db = load_db()
    user_id = str(m.from_user.id)
    user_appeals = [f"🆔 **{aid}**\n📂 Toifa: {info['category']}\n🟢 Status: {info['status']}" + (f"\n⚠️ Sabab: {info['reason']}" if info.get('reason') else "") for aid, info in db.items() if str(info['user_id']) == user_id]
    
    if not user_appeals:
        await m.answer("Sizda hech qanday murojaat mavjud emas.")
    else:
        await m.answer("📋 Sizning murojaatlaringiz:\n\n" + "\n\n---\n\n".join(user_appeals), parse_mode="Markdown")

@dp.message(Form.fio, F.text)
async def fio(m: types.Message, state: FSMContext):
    fio_text = m.text.strip()
    if len(fio_text) < 3:
        await m.answer("F.I.SH juda qisqa. Iltimos, to'liq ism-sharifingizni kiriting:")
        return
    await state.update_data(fio=fio_text)
    await m.answer("MFY tanlang:", reply_markup=mfy_page_kb(0))
    await state.set_state(Form.mfy)

@dp.callback_query(Form.mfy, F.data.startswith("page|"))
async def mfy_page_nav(call: types.CallbackQuery):
    page = int(call.data.split("|")[1])
    try:
        await call.message.edit_reply_markup(reply_markup=mfy_page_kb(page))
    except TelegramBadRequest:
        pass
    await call.answer()

@dp.callback_query(Form.mfy, F.data.startswith("mfy|"))
async def mfy_choose(call: types.CallbackQuery, state: FSMContext):
    idx = int(call.data.split("|")[1])
    mfy_name = MFY_LIST[idx]
    await state.update_data(mfy=mfy_name)
    try:
        await call.message.edit_text(f"✅ MFY: {mfy_name}")
    except TelegramBadRequest:
        pass
    await call.message.answer("Toifa tanlang:", reply_markup=category_kb())
    await state.set_state(Form.category)
    await call.answer()

@dp.callback_query(Form.category, F.data.startswith("cat|"))
async def cat(call: types.CallbackQuery, state: FSMContext):
    code = call.data.split("|")[1]
    name = CATEGORY_NAMES.get(code)
    await state.update_data(category=name)
    try:
        await call.message.edit_text(f"✅ Toifa: {name}")
    except TelegramBadRequest:
        pass
    await call.message.answer("Telefon raqamingizni yuboring yoki o'tkazing:", reply_markup=contact_kb())
    await state.set_state(Form.contact)
    await call.answer()

@dp.message(Form.contact, F.contact)
async def contact_received(m: types.Message, state: FSMContext):
    await state.update_data(phone=m.contact.phone_number)
    await m.answer("Qo'shimcha telefon raqami bo'lsa kiriting (yoki 'yo'q' deb yozing):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.extra)

@dp.message(Form.contact, F.text == SKIP_TEXT)
async def contact_skipped(m: types.Message, state: FSMContext):
    await state.update_data(phone="Kiritilmadi")
    await m.answer("Qo'shimcha telefon raqami bo'lsa kiriting (yoki 'yo'q' deb yozing):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.extra)

@dp.message(Form.extra, F.text)
async def extra(m: types.Message, state: FSMContext):
    await state.update_data(extra=m.text.strip())
    await m.answer("Murojaatingizni batafsil yozing:")
    await state.set_state(Form.text)

@dp.message(Form.text, F.text)
async def final(m: types.Message, state: FSMContext):
    appeal_text = m.text.strip()
    if len(appeal_text) < 5:
        await m.answer("Murojaat matni juda qisqa. Iltimos, batafsil yozing:")
        return

    data = await state.get_data()
    appeal_id = generate_unique_id()

    appeal_data = {
        "appeal_id": appeal_id,
        "user_id": m.from_user.id,
        "fio": data.get('fio'),
        "mfy": data.get('mfy'),
        "category": data.get('category'),
        "phone": data.get('phone'),
        "extra": data.get('extra'),
        "text": appeal_text,
        "status": "Yuborildi",
        "reason": ""
    }

    # 1. Local JSON bazaga saqlash
    db = load_db()
    db[appeal_id] = appeal_data
    save_db(db)

    # 2. Cloud Supabase bazasiga saqlash
    if supabase:
        try:
            supabase.table("murojaatlar").insert(appeal_data).execute()
            logger.info(f"{appeal_id} murojaati Supabase'ga yozildi.")
        except Exception as e:
            logger.error(f"Supabase'ga yozishda xatolik: {e}")

    # Adminga xabar yuborish
    admin_text = (
        f"📨 YANGI MUROJAAT\n\n"
        f"🆔 ID: {appeal_id}\n"
        f"👤 F.I.SH: {data.get('fio')}\n"
        f"🏘 MFY: {data.get('mfy')}\n"
        f"📂 Toifa: {data.get('category')}\n"
        f"📱 Telefon: {data.get('phone')}\n"
        f"☎ Qo'shimcha: {data.get('extra')}\n\n"
        f"📝 Murojaat matni:\n{appeal_text}\n\n"
        f"⚙️ Amallarni bajarish uchun botga shunchaki murojaat ID raqamini yozib yuboring (Masalan: {appeal_id})"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception:
        logger.exception("Adminga xabar yuborishda xatolik")

    await m.answer(
        f"✅ Murojaatingiz qabul qilindi!\n🆔 Murojaat raqami: {appeal_id}\nStatus: Yuborildi\n\n"
        f"Murojaat holatini tekshirish uchun /holat buyrug'ini bosing.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()

# ================= ADMIN PROCESS (ID ORQALI BOSHQARISH) =================
@dp.message(F.chat.id == ADMIN_ID, F.text.regexp(r'^\d{4}$'))
async def admin_find_appeal(m: types.Message):
    appeal_id = m.text.strip()
    db = load_db()
    
    if appeal_id not in db:
        await m.answer("❌ Bunday ID ga ega murojaat topilmadi.")
        return
        
    app = db[appeal_id]
    info_text = (
        f"📋 MUROJAAT MA'LUMOTLARI ({appeal_id})\n\n"
        f"👤 F.I.SH: {app['fio']}\n"
        f"🏘 MFY: {app['mfy']}\n"
        f"📂 Toifa: {app['category']}\n"
        f"📱 Telefon: {app['phone']} | {app['extra']}\n"
        f"🟢 Status: {app['status']}\n"
        f"📝 Matni: {app['text']}\n"
    )
    if app.get('reason'):
        info_text += f"⚠️ Rad etish sababi: {app['reason']}\n"

    await m.answer(info_text, reply_markup=admin_action_kb(appeal_id))

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("adm_accept|"))
async def admin_accept(call: types.CallbackQuery):
    appeal_id = call.data.split("|")[1]
    db = load_db()
    if appeal_id in db:
        db[appeal_id]["status"] = "Qabul qilindi"
        save_db(db)
        
        if supabase:
            try:
                supabase.table("murojaatlar").update({"status": "Qabul qilindi"}).eq("appeal_id", appeal_id).execute()
            except Exception as e:
                logger.error(f"Supabase update xatosi: {e}")

        await call.message.edit_text(call.message.text + "\n\n🟢 Status o'zgartirildi: Qabul qilindi")
        try:
            await bot.send_message(db[appeal_id]["user_id"], f"✅ Sizning {appeal_id}-sonli murojaatingiz admin tomonidan QABUL QILINDI.")
        except Exception:
            pass
    await call.answer()

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("adm_reject|"))
async def admin_reject_start(call: types.CallbackQuery, state: FSMContext):
    appeal_id = call.data.split("|")[1]
    await state.update_data(reject_id=appeal_id)
    await state.set_state(AdminState.waiting_for_reject_reason)
    await call.message.answer("⚠️ Murojaatni rad etish sababini yozib yuboring:")
    await call.answer()

@dp.message(AdminState.waiting_for_reject_reason, F.text)
async def admin_reject_reason_received(m: types.Message, state: FSMContext):
    state_data = await state.get_data()
    appeal_id = state_data.get("reject_id")
    reason = m.text.strip()
    
    db = load_db()
    if appeal_id in db:
        db[appeal_id]["status"] = "Rad etildi"
        db[appeal_id]["reason"] = reason
        save_db(db)
        
        if supabase:
            try:
                supabase.table("murojaatlar").update({"status": "Rad etildi", "reason": reason}).eq("appeal_id", appeal_id).execute()
            except Exception as e:
                logger.error(f"Supabase update xatosi: {e}")

        await m.answer(f"❌ Murojaat rad etildi. Sababi foydalanuvchiga yuborildi.")
        try:
            await bot.send_message(db[appeal_id]["user_id"], f"❌ Sizning {appeal_id}-sonli murojaatingiz RAD ETILDI.\n⚠️ Sababi: {reason}")
        except Exception:
            pass
    await state.clear()

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("adm_close|"))
async def admin_close(call: types.CallbackQuery):
    appeal_id = call.data.split("|")[1]
    db = load_db()
    if appeal_id in db:
        db[appeal_id]["status"] = "Hal etildi"
        save_db(db)
        
        if supabase:
            try:
                supabase.table("murojaatlar").update({"status": "Hal etildi"}).eq("appeal_id", appeal_id).execute()
            except Exception as e:
                logger.error(f"Supabase update xatosi: {e}")

        await call.message.edit_text(call.message.text + "\n\n🏁 Murojaat yopildi: Hal etildi")
        try:
            await bot.send_message(db[appeal_id]["user_id"], f"🏁 Sizning {appeal_id}-sonli murojaatingiz yuzasidan javob berildi va muammo HAL ETILDI. Rahmat!")
        except Exception:
            pass
    await call.answer()

# ================= FALLBACKS & RUN =================
@dp.message()
async def fallback(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("Boshqarish uchun 4 xonali murojaat ID raqamini yozing.")
    else:
        await m.answer("Murojaat yuborish uchun /start , holatni tekshirish uchun /holat buyrug'ini bosing.")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi topilmadi!")
    logger.info("Bot ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
