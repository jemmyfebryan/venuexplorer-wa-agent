import asyncio
import re
import os
import signal
from wa_automate_socket_client import SocketClient
from core.open_wa.listener import ChatBotHandler
from core.agent.handler import (
    chat_inquiry,
    chat_inquiry_next,
    book_selected_venue
)
from core.logger import get_logger

logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()

OPEN_WA_PORT = os.getenv("OPEN_WA_PORT")

book_pattern = re.compile(r"^book (\d+)$", re.IGNORECASE)
    
async def extract_book_number(text: str) -> int | None:
    match = book_pattern.match(text.strip())
    if match:
        return int(match.group(1))
    return None

async def main():
    logger.info("🚀 Starting WhatsApp bot...")
    client = SocketClient(f"http://172.17.0.1:{OPEN_WA_PORT}/", api_key="my_secret_api_key")
    bot = ChatBotHandler(client)

    @bot.on(r"^inquiry")
    async def inquiry(msg, client, history):
        if not msg["data"]["isGroupMsg"]:
            message = msg["data"].get("body", "")
            user_name = msg["data"].get("sender").get("name")
            phone_number = msg["data"].get("from").split("@")[0]
            logger.info(f"Book Venue! message: {message}, user_name: {user_name}, phone_number: {phone_number}")
            response = await chat_inquiry(
                user_name=user_name,
                message=message,
                phone_number=phone_number
            )
            await client.sendText(msg["data"]["from"], response)

    @bot.on(r"^book \d+$")
    async def book_venue(msg, client, history):
        # try:
        if not msg["data"]["isGroupMsg"]:
            message = msg["data"].get("body", "")
            # user_name = msg["data"].get("sender").get("name")
            user_from = msg["data"].get("from")
            # logger.info(f"User_From: {user_from}")
            # phone_number = msg["data"].get("from").split("@")[0]
            logger.info(f"Book Venue! message: {message}, user_from: {user_from}")
            last_response = client.getMyLastMessage(user_from)
            # logger.info(f"Last_Response: {last_response}")
            book_number = await extract_book_number(text=message)
            response = await book_selected_venue(
                selected_venue_index=book_number,
                inquiry_chat=last_response.get("body")
            )
            await client.sendText(msg["data"]["from"], response)
            
    @bot.on(r"^book next$")
    async def book_next(msg, client, history):
        # try:
        if not msg["data"]["isGroupMsg"]:
            message = msg["data"].get("body", "")
            user_name = msg["data"].get("sender").get("name")
            user_from = msg["data"].get("from")
            phone_number = msg["data"].get("from").split("@")[0]
            logger.info(f"Book Next! message: {message}, user_name: {user_name}, phone_number: {phone_number}")
            last_response = client.getMyLastMessage(user_from).get("body")
            
            response = await chat_inquiry_next(
                user_name=user_name,
                phone_number=phone_number,
                last_message=last_response
            )
            
            await client.sendText(msg["data"]["from"], response)
        
    

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
