from wa_automate_socket_client import SocketClient

def get_new_messages(
    open_wa_client: SocketClient,
    include_group_messages: bool = False,
    include_from_me: bool = False,
    retrieved_keys: set = {"id", "from", "to", "text", "mId", "notifyName"}
):
    raw_messages = open_wa_client.getAllNewMessages()
    
    # Filter messages
    message_filter = {
        "isGroupMsg": include_group_messages,
        "fromMe": include_from_me,
    }
    
    filtered_messages = [
        msg
        for msg in raw_messages
        if all(msg.get(k) == v for k, v in message_filter.items())
    ]

    # Filter important keys
    filtered_messages = [
        {k: msg[k] for k in retrieved_keys if k in msg}
        for msg in filtered_messages
    ]
    
    final_messages = filtered_messages
    
    return final_messages
