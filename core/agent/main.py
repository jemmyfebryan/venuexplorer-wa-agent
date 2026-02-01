import asyncio
import re
import os
import signal
from wa_automate_socket_client import SocketClient

from core.openai import create_client
from core.open_wa.listener import ChatBotHandler
from core.agent.handler import (
    chat_inquiry,
    chat_inquiry_next,
    book_selected_venue
)
from core.logger import get_logger

from core.agent.session import chat_response

logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()

openai_client = create_client()

OPEN_WA_HOST = os.getenv("OPEN_WA_HOST", "172.17.0.1")
OPEN_WA_PORT = os.getenv("OPEN_WA_PORT", "8003")

book_pattern = re.compile(r"^book (\d+)$", re.IGNORECASE)
    
async def extract_book_number(text: str) -> int | None:
    match = book_pattern.match(text.strip())
    if match:
        return int(match.group(1))
    return None

async def init_openwa_client() -> SocketClient:
    """
    Initialize the OpenWA SocketClient in a non-blocking way.
    Returns the initialized client instead of using a global.
    """
    loop = asyncio.get_event_loop()

    def blocking_init():
        client = SocketClient(
            f"http://{OPEN_WA_HOST}:{OPEN_WA_PORT}/",
            api_key="my_secret_api_key",
        )
        return client

    client = await loop.run_in_executor(None, blocking_init)
    return client

async def main():
    logger.info("🚀 Starting WhatsApp bot...")
    # client = SocketClient(f"http://172.17.0.1:{OPEN_WA_PORT}/", api_key="my_secret_api_key")
    client = await init_openwa_client()
    bot = ChatBotHandler(client)
    
    @bot.on(r"")
    async def conv_handler(msg, client, history):
        # we ignore group messages here
        if msg.get("data", {}).get("isGroupMsg") or msg["data"]["fromMe"]:
            return
        
        await chat_response(
            msg=msg,
            client=client,
            openai_client=openai_client,
        )

    logger.info("✅ Bot is running. Waiting for messages...")

    # Graceful shutdown handler
    async def shutdown():
        logger.info("🛑 Shutting down socket client...")
        client.disconnect()
        logger.info("✅ Socket client disconnected.")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    # Keep the loop alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
