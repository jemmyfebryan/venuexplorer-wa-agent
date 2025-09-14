from wa_automate_socket_client import SocketClient

from core.open_wa.listener import ChatBotHandler

client = SocketClient('http://localhost:8003/', api_key="my_secret_api_key")
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

# fallback if nothing matches
def fallback(msg, client, history):
    if msg["data"]["isGroupMsg"] == False and msg["data"]["fromMe"] == False:
        client.sendText(msg["data"]["from"], "I didn't understand that 🤔")
bot.set_fallback(fallback)

# run loop
import time
while True:
    time.sleep(1)
