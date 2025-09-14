from wa_automate_socket_client import SocketClient
from core.open_wa.listener import ChatBotHandler

print("🚀 Starting WhatsApp bot...", flush=True)
client = SocketClient('http://172.17.0.1:8003/', api_key="my_secret_api_key")
print("✅ SocketClient connected", flush=True)
bot = ChatBotHandler(client)


@bot.on(r"^hi|hello$")
def greet(msg, client, history):
    return "Hello 👋 How can I help you?"


@bot.on(r"^ping$")
def ping(msg, client, history):
    return "pong 🏓"


@bot.on(r"^bye$")
def bye(msg, client, history):
    return "Goodbye 👋"


def fallback(msg, client, history):
    if msg["data"]["isGroupMsg"] is False and msg["data"]["fromMe"] is False:
        return "I didn't understand that 🤔"


bot.set_fallback(fallback)
