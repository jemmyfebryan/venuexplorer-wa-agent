from wa_automate_socket_client import SocketClient

NUMBER = 'TEST_PHONE_NUMBER@c.us'

client = SocketClient('http://localhost:8003/', 'my_secret_api_key')

def printResponse(message):
    print(message)

import json

last_response = client.getAllMessagesInChat("6285850434383@c.us", True, True)
print(json.dumps(last_response, indent=2))



# # Listening for events
# client.onMessage(printResponse)

# # Executing commands
# client.sendText(NUMBER, "this is a text")

# # Sync/Async support
# print(client.getHostNumber())  # Sync request
# client.sendAudio(NUMBER,
#                  "https://download.samplelib.com/mp3/sample-3s.mp3",
#                  sync=False,
#                  callback=printResponse)  # Async request. Callback is optional

# Finally disconnect
client.disconnect()