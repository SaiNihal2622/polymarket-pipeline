"""
Click the Top Holders button for several markets to extract whale wallet addresses.
"""
import asyncio, sys
from telethon import TelegramClient
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"

KEYWORDS = ["bitcoin", "trump", "ethereum", "nba", "soccer", "ipl", "fed rate", "solana"]

async def click_button(client, msg, btn_data: bytes):
    try:
        result = await client(GetBotCallbackAnswerRequest(
            peer="@polycoolapp_bot",
            msg_id=msg.id,
            data=btn_data,
        ))
        return result.message or ""
    except Exception as e:
        return f"err: {e}"

async def main():
    client = TelegramClient("polycool_session", API_ID, API_HASH)
    await client.start()
    bot = "@polycoolapp_bot"

    for kw in KEYWORDS:
        sys.stdout.buffer.write(f"\n{'='*50}\n/market {kw}\n{'='*50}\n".encode())
        await client.send_message(bot, f"/market {kw}")
        await asyncio.sleep(6)

        msgs = await client.get_messages(bot, limit=5)
        # Find the bot reply with buttons
        for m in msgs:
            if not m.reply_markup or not m.text:
                continue
            if "Yes" not in m.text and "No" not in m.text:
                continue
            sys.stdout.buffer.write(f"MARKET: {m.text[:400]}\n".encode())

            # Click Top Holders button
            for row in m.reply_markup.rows:
                for btn in row.buttons:
                    btn_data = getattr(btn, 'data', b'')
                    if btn_data and btn_data.startswith(b'holders:'):
                        sys.stdout.buffer.write(f"  >> Clicking Top Holders ({btn_data.decode()})...\n".encode())
                        answer = await click_button(client, m, btn_data)
                        sys.stdout.buffer.write(f"  ANSWER: {str(answer)[:800]}\n".encode())
            break

    await client.disconnect()

asyncio.run(main())
