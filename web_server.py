import asyncio
import aiohttp
from aiohttp import web
import os

routes = web.RouteTableDef()

# Asosiy route (Render tekshiradigan manzil)
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "alive", "bot": "kino_bot"})

@routes.get("/ping")
async def ping_handler(request):
    return web.json_response({"status": "pong", "message": "Bot is alive"})

@routes.get("/health")
async def health_handler(request):
    return web.json_response({"status": "healthy", "service": "telegram_bot"})

# Veb-serverni ishga tushiruvchi funksiya
async def web_server():
    app = web.Application()
    app.add_routes(routes)

    # 🔁 Bot o'zini har 10 daqiqada ping qiladi
    async def self_ping():
        await asyncio.sleep(20)  # bot to'liq yuklanishini kutadi
        url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME') or 'your-app-name.onrender.com'}"
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{url}/ping") as resp:
                        print(f"[PING] {url} → {resp.status}")
            except Exception as e:
                print(f"[PING ERROR] {e}")
            await asyncio.sleep(600)  # har 10 daqiqada ping (600 sekund)

    asyncio.create_task(self_ping())  # 🔄 fon jarayon sifatida ishlaydi
    
    return app

# Serverni ishga tushirish
async def start_server():
    app = await web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🌐 aiohttp server 8080 portda ishga tushdi")
    return runner

# Asosiy ishga tushirish
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        runner = loop.run_until_complete(start_server())
        print("🚀 Server ishga tushdi...")
        loop.run_forever()
    except KeyboardInterrupt:
        print("⏹️ Server to'xtatilmoqda...")
    finally:
        loop.run_until_complete(runner.cleanup())
        loop.close()