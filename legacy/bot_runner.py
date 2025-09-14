import asyncio
from wa_automate_socket_client import SocketClient
from core.open_wa.listener import ChatBotHandler

async def main():
    print("🚀 Starting WhatsApp bot...", flush=True)
    client = SocketClient("http://172.17.0.1:8003/", api_key="my_secret_api_key")
    bot = ChatBotHandler(client)

    @bot.on(r"^hi|hello$")
    def greet(msg, client, history):
        client.sendText(msg["data"]["from"], "Hello 👋 How can I help you?")

    @bot.on(r"^ping$")
    def ping(msg, client, history):
        client.sendText(msg["data"]["from"], "pong 🏓")

    @bot.on(r"^bye$")
    def bye(msg, client, history):
        client.sendText(msg["data"]["from"], "Goodbye 👋")

    def fallback(msg, client, history):
        if msg["data"]["isGroupMsg"] is False and msg["data"]["fromMe"] is False:
            client.sendText(msg["data"]["from"], "I didn't understand that 🤔")

    bot.set_fallback(fallback)

    print("✅ Bot is running. Waiting for messages...", flush=True)

    # Keep the loop alive forever
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
