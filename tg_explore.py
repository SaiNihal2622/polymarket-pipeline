import asyncio, sys
from telethon import TelegramClient

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"

async def main():
    client = TelegramClient("polycool_session", API_ID, API_HASH)
    await client.start()
    bot = "@polycoolapp_bot"

    commands = ["/help", "/top", "/leaderboard", "/whales", "/signals", "/trades", "/wallets", "/markets"]

    for cmd in commands:
        await client.send_message(bot, cmd)
        await asyncio.sleep(5)
        msgs = await client.get_messages(bot, limit=6)
        sys.stdout.buffer.write(f"\n=== {cmd} ===\n".encode("utf-8"))
        for m in reversed(msgs):
            if m.text:
                sys.stdout.buffer.write(f"BOT: {m.text[:1000]}\n".encode("utf-8"))

    await client.disconnect()

asyncio.run(main())
