from fastapi import FastAPI, Request
from bot import bot, client

app = FastAPI()


@app.post("/message")
async def receive_message(request: Request):
    """
    This endpoint receives a message JSON (from your WhatsApp socket client),
    runs it through ChatBotHandler, and returns the bot's response.
    """
    msg = await request.json()

    # Let the ChatBotHandler process the message
    response_text = bot.handle(msg)  # ChatBotHandler should return the matching response

    # Optionally: send back via WhatsApp automatically
    if response_text:
        client.sendText(msg["data"]["from"], response_text)

    return {"response": response_text or ""}
