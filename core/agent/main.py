import asyncio
import re
import os
import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from core.openai import create_client
from core.logger import get_logger
from core.agent.session import chat_response

logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()

openai_client = create_client()

OPEN_WA_HOST = os.getenv("OPEN_WA_HOST", "172.17.0.1")
OPEN_WA_PORT = os.getenv("OPEN_WA_PORT", "8003")
OPEN_WA_API_KEY = os.getenv("OPEN_WA_API_KEY", "my_secret_api_key")
BOT_PORT = int(os.getenv("BOT_PORT", "8000"))

OPEN_WA_BASE_URL = f"http://{OPEN_WA_HOST}:{OPEN_WA_PORT}"

book_pattern = re.compile(r"^book (\d+)$", re.IGNORECASE)


class OpenWAClient:
    """HTTP client for open-wa REST API"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def sendText(self, to: str, content: str):
        """Send a text message - matches the SocketClient API"""
        url = f"{self.base_url}/sendText"
        payload = {
            "args": {
                "to": to,
                "content": content
            }
        }
        headers = {"api_key": self.api_key}
        try:
            response = await self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise
    
    async def close(self):
        await self.client.aclose()


# Global client instance
wa_client: OpenWAClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global wa_client
    
    logger.info("🚀 Starting WhatsApp bot...")
    logger.info(f"📡 OPEN_WA_HOST={OPEN_WA_HOST}, OPEN_WA_PORT={OPEN_WA_PORT}")
    
    # Initialize the HTTP client
    wa_client = OpenWAClient(OPEN_WA_BASE_URL, OPEN_WA_API_KEY)
    logger.info(f"✅ OpenWA client initialized: {OPEN_WA_BASE_URL}")
    
    # Register webhook with open-wa
    await register_webhook()
    
    logger.info("✅ Bot is running. Waiting for messages...")
    
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down...")
    if wa_client:
        await wa_client.close()
    logger.info("✅ Bot stopped.")


app = FastAPI(lifespan=lifespan)


async def register_webhook():
    """Register this bot as a webhook receiver with open-wa"""
    # Get the container's IP on the docker bridge network
    bot_webhook_url = os.getenv("BOT_WEBHOOK_URL")
    
    if not bot_webhook_url:
        # Try to auto-detect - the bot container IP that open-wa can reach
        logger.info("💡 BOT_WEBHOOK_URL not set, attempting auto-registration...")
        # open-wa container needs to reach wa_bot_container
        # They're both on bridge network, so use container IP or docker gateway
        bot_webhook_url = f"http://172.17.0.1:{BOT_PORT}/webhook"
    
    logger.info(f"📝 Registering webhook: {bot_webhook_url}")
    
    # Try the /webhook endpoint first
    url = f"{OPEN_WA_BASE_URL}/webhook"
    payload = {
        "args": {
            "url": bot_webhook_url,
            "events": ["onAnyMessage", "onMessage"]
        }
    }
    headers = {"api_key": OPEN_WA_API_KEY}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"📝 Webhook registration response: {response.status_code}")
            if response.status_code == 200:
                logger.info("✅ Webhook registered successfully!")
            else:
                logger.warning(f"⚠️ Webhook registration returned: {response.text}")
    except Exception as e:
        logger.warning(f"⚠️ Could not register webhook automatically: {e}")
        logger.info(f"💡 You may need to manually configure open-wa webhook to: {bot_webhook_url}")


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming webhook events from open-wa"""
    try:
        data = await request.json()
        event = data.get("event", "unknown")
        logger.info(f"📨 Received webhook event: {event}")
        
        # Only process onMessage event (ignore onAnyMessage to avoid duplicates)
        # open-wa sends BOTH events for each message
        if event == "onMessage":
            msg_data = data.get("data", {})
            
            # Debug: log the full message structure to understand the format
            logger.info(f"📋 Full message data keys: {list(msg_data.keys()) if isinstance(msg_data, dict) else type(msg_data)}")
            logger.info(f"📋 'from' field: {msg_data.get('from')}")
            logger.info(f"📋 'chatId' field: {msg_data.get('chatId')}")
            logger.info(f"📋 'id' field: {msg_data.get('id')}")
            
            # Skip group messages and messages from self
            if msg_data.get("isGroupMsg") or msg_data.get("fromMe"):
                logger.debug("Skipping group/self message")
                return {"status": "ignored"}
            
            sender = msg_data.get("from", "unknown")
            body = msg_data.get("body", "")
            logger.info(f"📩 Message from {sender}: {body[:50]}...")
            
            # Process the message
            await process_message(msg_data)
        elif event == "onAnyMessage":
            # Skip onAnyMessage to avoid duplicate processing
            logger.debug("Skipping onAnyMessage (using onMessage instead)")
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return {"status": "error", "message": str(e)}


async def process_message(msg: dict):
    """Process an incoming message"""
    try:
        # Wrap message in expected format for chat_response
        wrapped_msg = {"data": msg}
        
        await chat_response(
            msg=wrapped_msg,
            client=wa_client,
            openai_client=openai_client,
        )
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "open_wa_url": OPEN_WA_BASE_URL}


@app.get("/")
async def root():
    return {"message": "WhatsApp Bot is running", "webhook_path": "/webhook"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=BOT_PORT)
