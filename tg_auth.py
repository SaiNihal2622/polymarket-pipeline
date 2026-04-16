"""
One-time Telegram authentication.
python tg_auth.py
"""
import asyncio
import sys
from telethon import TelegramClient

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"
PHONE    = "+916305842166"

async def main():
    client = TelegramClient("polycool_session", API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        await client.send_code_request(PHONE)
        code = input("Enter the Telegram code: ").strip()
        await client.sign_in(PHONE, code)

    print("Authenticated! Session saved.")

    bot = "@polycoolapp_bot"
    for cmd in ["/start", "/help", "/leaderboard"]:
        print(f"\n>>> Sending {cmd}")
        await client.send_message(bot, cmd)
        await asyncio.sleep(5)
        msgs = await client.get_messages(bot, limit=5)
        for m in reversed(msgs):
            if m.text:
                print(f"BOT: {m.text[:800]}")

    await client.disconnect()

asyncio.run(main())
