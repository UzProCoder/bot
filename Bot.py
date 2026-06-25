import asyncio
import logging
import random
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
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
from supabase import create_client, Client

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", 1973341892))
except (ValueError, TypeError):
    ADMIN_ID = 1973341892

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("gls_bot")

# Supabase mijozini ulash
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# ================= UTILS (MARKDOWN ESCAPE) =================
def escape_markdown(text: str) -> str:
    """Markdown v1 formatida xatolik bermasligi uchun maxsus belgilarni tozalash"""
    if not text:
        return ""
    for char in ['_', '*', '`', '[']:
        text = text.replace(char, f"\\{char}")
    return text

# ================= ASYNC SUPABASE INTEGRATION =================
async def get_appeal(appeal_id: str):
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None, 
            lambda: supabase.table("murojaatlar").select("*").eq("appeal_id", appeal_id).execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Supabase get_appeal xatolik: {e}")
        return None

async def get_user_appeals(user_id: int):
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None, 
            lambda: supabase.table("murojaatlar").select("*").eq("user_id", user_id).execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Supabase get_user_appeals xatolik: {e}")
        return []

async def insert_appeal(data: dict):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None, 
            lambda: supabase.table("murojaatlar").insert(data).execute()
        )
        return True
    except Exception as e:
        logger.error(f"Supabase insert_appeal xatolik: {e}")
        return False

async def update_appeal_status(appeal_id: str, status: str, reason: str = ""):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None, 
            lambda: supabase.table("murojaatlar").update({"status": status, "reason": reason}).eq("appeal_id", appeal_id).execute()
        )
        return True
    except Exception as e:
        logger.error(f"Supabase update_appeal_status xatolik: {e}")
        return False

async def generate_unique_id():
    while True:
        short_id = str(random.randint(1000, 9999))
        if not await get_appeal(short_id):
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
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CONTACT_BUTTON_TEXT, request_contact=True)], 
            [KeyboardButton(text=SKIP_TEXT)]
        ], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

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
    await m.answer(
        "Assalomu alaykum! Murojaat qabul qilish botiga xush kiribsiz.\n\nF.I.SH kiriting (Ism va familiyangizni to'liq yozing):", 
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.fio)

@dp.message(F.text == "/holat")
async def check_status(m: types.Message, state: FSMContext):
    await state.clear()  # Holatni tozalash, jarayon qotib qolmasligi uchun
    appeals = await get_user_appeals(m.from_user.id)
    
    if not appeals:
        await m.answer("Sizda hech qanday murojaat mavjud emas.")
        return

    user_appeals = []
    for app in appeals:
        text_block = (
            f"🆔 *{escape_markdown(app['appeal_id'])}*\n"
            f"📂 Toifa: {escape_markdown(app['category'])}\n"
            f"🟢 Status: {escape_markdown(app['status'])}"
        )
        if app.get('reason'):
            text_block += f"\n⚠️ Sabab: {escape_markdown(app['reason'])}"
        user_appeals.append(text_block)

    await m.answer("📋 Sizning murojaatlaringiz:\n\n" + "\n\n---\n\n".join(user_appeals), parse_mode="Markdown")

@dp.message(Form.fio, F.text)
async def fio(m: types.Message, state: FSMContext):
    fio_text = m.text.strip()
    if len(fio_text) < 3:
        await m.answer("F.I.SH juda qisqa. Iltimos, to'liq ism-sharifingizni kiriting:")
        return
    await state.update_data(fio=fio_text)
    await m.answer("Yashash MFY (Mahalla fuqarolar yig'ini)ni tanlang:", reply_markup=mfy_page_kb(0))
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
    if idx < 0 or idx >= len(MFY_LIST):
        await call.answer("Xatolik! Qaytadan urinib ko'ring.", show_alert=True)
        return
    mfy_name = MFY_LIST[idx]
    await state.update_data(mfy=mfy_name)
    try:
        await call.message.edit_text(f"✅ MFY: {mfy_name}")
    except TelegramBadRequest:
        pass
    await call.message.answer("Murojaat toifasini tanlang:", reply_markup=category_kb())
    await state.set_state(Form.category)
    await call.answer()

@dp.callback_query(Form.category, F.data.startswith("cat|"))
async def cat(call: types.CallbackQuery, state: FSMContext):
    code = call.data.split("|")[1]
    name = CATEGORY_NAMES.get(code)
    if not name:
        await call.answer("Noto'g'ri toifa!", show_alert=True)
        return
    await state.update_data(category=name)
    try:
        await call.message.edit_text(f"✅ Toifa: {name}")
    except TelegramBadRequest:
        pass
    await call.message.answer("Aloqa uchun telefon raqamingizni yuboring (yoki o'tkazib yuboring):", reply_markup=contact_kb())
    await state.set_state(Form.contact)
    await call.answer()

@dp.message(Form.contact, F.contact)
async def contact_received(m: types.Message, state: FSMContext):
    await state.update_data(phone=m.contact.phone_number)
    await m.answer("Qo'shimcha telefon raqamingiz bo'lsa kiriting (agar yo'q bo'lsa, 'yo'q' deb yozing):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.extra)

@dp.message(Form.contact, F.text == SKIP_TEXT)
async def contact_skipped(m: types.Message, state: FSMContext):
    await state.update_data(phone="Kiritilmadi")
    await m.answer("Qo'shimcha telefon raqamingiz bo'lsa kiriting (agar yo'q bo'lsa, 'yo'q' deb yozing):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.extra)

@dp.message(Form.extra, F.text)
async def extra(m: types.Message, state: FSMContext):
    await state.update_data(extra=m.text.strip())
    await m.answer("Murojaatingiz matnini batafsil va tushunarli qilib yozing:")
    await state.set_state(Form.text)

@dp.message(Form.text, F.text)
async def final(m: types.Message, state: FSMContext):
    appeal_text = m.text.strip()
    if len(appeal_text) < 5:
        await m.answer("Murojaat matni juda qisqa. Iltimos, batafsilroq yozing:")
        return

    data = await state.get_data()
    appeal_id = await generate_unique_id()

    # Supabase-ga xavfsiz saqlash
    success = await insert_appeal({
        "appeal_id": appeal_id,
        "user_id": m.from_user.id,
        "fio": data.get('fio'),
        "mfy": data.get('mfy'),
        "category": data.get('category'),
        "phone": data.get('phone'),
        "extra": data.get('extra'),
        "text": appeal_text,
        "status": "Yuborildi"
    })

    if not success:
        await m.answer("⚠️ Tizimda texnik xatolik yuz berdi. Arizangizni saqlab bo'lmadi. Iltimos, qaytadan /start buyrug'ini bosing.")
        await state.clear()
        return

    admin_text = (
        f"📨 YANGI MUROJAAT\n\n"
        f"🆔 ID: {appeal_id}\n"
        f"👤 F.I.SH: {data.get('fio')}\n"
        f"🏘 MFY: {data.get('mfy')}\n"
        f"📂 Toifa: {data.get('category')}\n"
        f"📱 Telefon: {data.get('phone')}\n"
        f"☎ Qo'shimcha: {data.get('extra')}\n\n"
        f"📝 Murojaat matni:\n{appeal_text}\n\n"
        f"⚙️ Amallarni bajarish uchun ushbu 4 xonali murojaat ID raqamini botga oddiy matn qilib yuboring: {appeal_id}"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception as e:
        logger.error(f"Adminga xabar ketmadi: {e}")

    await m.answer(
        f"✅ Murojaatingiz muvaffaqiyatli qabul qilindi!\n🆔 Murojaat raqami: {appeal_id}\nStatus: Yuborildi\n\n"
        f"Murojaat holatini tekshirish uchun istalgan vaqtda /holat buyrug'ini bosing.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()

# ================= ADMIN PROCESS (SECURITY ENHANCED) =================
@dp.message(F.chat.id == ADMIN_ID, F.text.regexp(r'^\d{4}$'))
async def admin_find_appeal(m: types.Message, state: FSMContext):
    await state.clear()  # Admin adashib boshqa holatda qolib ketgan bo'lsa tozalaydi
    appeal_id = m.text.strip()
    app = await get_appeal(appeal_id)
    
    if not app:
        await m.answer("❌ Bunday ID ga ega murojaat ma'lumotlar bazasidan topilmadi.")
        return
        
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
    app = await get_appeal(appeal_id)
    if app:
        await update_appeal_status(appeal_id, "Qabul qilindi")
        try:
            await call.message.edit_text(call.message.text + "\n\n🟢 Status o'zgartirildi: Qabul qilindi")
        except TelegramBadRequest:
            pass
        try:
            await bot.send_message(app["user_id"], f"✅ Sizning {appeal_id}-sonli murojaatingiz mas'ul xodim tomonidan QABUL QILINDI.")
        except TelegramForbiddenError:
            logger.warning(f"Foydalanuvchi {app['user_id']} botni blocklagan.")
        except Exception:
            pass
    await call.answer()

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("adm_reject|"))
async def admin_reject_start(call: types.CallbackQuery, state: FSMContext):
    appeal_id = call.data.split("|")[1]
    await state.update_data(reject_id=appeal_id)
    await state.set_state(AdminState.waiting_for_reject_reason)
    await call.message.answer("⚠️ Ushbu murojaatni rad etish sababini yozib yuboring (Foydalanuvchiga ko'rinadi):")
    await call.answer()

@dp.message(AdminState.waiting_for_reject_reason, F.text, F.chat.id == ADMIN_ID)
async def admin_reject_reason_received(m: types.Message, state: FSMContext):
    state_data = await state.get_data()
    appeal_id = state_data.get("reject_id")
    reason = m.text.strip()
    
    app = await get_appeal(appeal_id)
    if app:
        await update_appeal_status(appeal_id, "Rad etildi", reason)
        await m.answer(f"❌ Murojaat rad etildi va sababi foydalanuvchiga xabar qilindi.")
        try:
            await bot.send_message(
                app["user_id"], 
                f"❌ Sizning {appeal_id}-sonli murojaatingiz RAD ETILDI.\n⚠️ Rad etilish sababi: {reason}"
            )
        except TelegramForbiddenError:
            logger.warning(f"Foydalanuvchi {app['user_id']} botni blocklagan.")
        except Exception:
            pass
    await state.clear()

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("adm_close|"))
async def admin_close(call: types.CallbackQuery):
    appeal_id = call.data.split("|")[1]
    app = await get_appeal(appeal_id)
    if app:
        await update_appeal_status(appeal_id, "Hal etildi")
        try:
            await call.message.edit_text(call.message.text + "\n\n🏁 Murojaat yopildi: Hal etildi")
        except TelegramBadRequest:
            pass
        try:
            await bot.send_message(
                app["user_id"], 
                f"🏁 Sizning {appeal_id}-sonli murojaatingiz yuzasidan tegishli chora-tadbirlar ko'rildi va muammo HAL ETILDI. Rahmat!"
            )
        except TelegramForbiddenError:
            logger.warning(f"Foydalanuvchi {app['user_id']} botni blocklagan.")
        except Exception:
            pass
    await call.answer()

# ================= FALLBACKS & RUN =================
@dp.message()
async def fallback(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("Murojaatni boshqarish yoki ko'rish uchun uning 4 xonali ID raqamini oddiy xabar qilib yozib yuboring (Masalan: 4321).")
    else:
        await m.answer("Murojaat yuborishni boshlash uchun /start yoki holatni tekshirish uchun /holat buyrug'ini bosing.")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi topilmadi. Uni Actions Secrets-ga yuklang!")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase ulanish ma'lumotlari (URL/KEY) Actions Secrets-da mavjud emas!")
        
    logger.info("Mukammal xavfsiz bot tizimi ishga tushdi.")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
