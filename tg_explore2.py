import asyncio, sys
from telethon import TelegramClient
from telethon.tl.types import MessageEntityUrl, ReplyInlineMarkup

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"

async def main():
    client = TelegramClient("polycool_session", API_ID, API_HASH)
    await client.start()
    bot = "@polycoolapp_bot"

    # Try market-specific commands
    test_cmds = [
        "/market bitcoin",
        "/market trump",
        "/top traders",
        "/leaderboard sports",
    ]

    for cmd in test_cmds:
        await client.send_message(bot, cmd)
        await asyncio.sleep(6)
        msgs = await client.get_messages(bot, limit=3)
        sys.stdout.buffer.write(f"\n=== {cmd} ===\n".encode("utf-8"))
        for m in reversed(msgs):
            # Print text
            if m.text:
                sys.stdout.buffer.write(f"TEXT: {m.text[:1500]}\n".encode("utf-8"))
            # Print inline buttons
            if m.reply_markup:
                try:
                    for row in m.reply_markup.rows:
                        for btn in row.buttons:
                            btn_text = getattr(btn, 'text', '')
                            btn_data = getattr(btn, 'data', b'')
                            btn_url  = getattr(btn, 'url', '')
                            sys.stdout.buffer.write(
                                f"  BTN: [{btn_text}] data={btn_data} url={btn_url}\n".encode("utf-8")
                            )
                except Exception as e:
                    sys.stdout.buffer.write(f"  markup err: {e}\n".encode("utf-8"))

    # Also dump last 20 messages to see full history
    sys.stdout.buffer.write(b"\n=== LAST 20 BOT MESSAGES ===\n")
    msgs = await client.get_messages(bot, limit=20)
    for m in reversed(msgs):
        if m.text:
            sys.stdout.buffer.write(f"[{m.date}] {m.text[:300]}\n".encode("utf-8"))
        if m.reply_markup:
            try:
                for row in m.reply_markup.rows:
                    for btn in row.buttons:
                        btn_text = getattr(btn, 'text', '')
                        btn_url  = getattr(btn, 'url', '')
                        btn_data = getattr(btn, 'data', b'')
                        sys.stdout.buffer.write(f"  BTN [{btn_text}] url={btn_url} data={btn_data}\n".encode("utf-8"))
            except Exception:
                pass

    await client.disconnect()

asyncio.run(main())
