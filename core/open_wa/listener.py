import re
import asyncio
import inspect

from wa_automate_socket_client import SocketClient

class MessageHandler:
    def __init__(self, open_wa_client: SocketClient):
        self.open_wa_client = open_wa_client
        self._handler = None

        # Register a stable wrapper ONCE
        def wrapper(msg):
            if self._handler:
                self._handler(msg)

        self.open_wa_client.onAnyMessage(wrapper)

    def set_handler(self, fn):
        """Replace the active handler dynamically"""
        self._handler = fn

class ChatBotHandler:
    def __init__(self, client: SocketClient):
        self.client = client
        self.routes = []   # list of (pattern, handler)
        self.fallback = None
        self.memory = {}   # per-user context

        self.loop = asyncio.get_event_loop()  # capture main loop

        async def wrapper(msg):
            text = msg["data"].get("body", "")
            user = msg["data"].get("from")

            if user not in self.memory:
                self.memory[user] = []
            self.memory[user].append(text)

            for pattern, handler in self.routes:
                if re.search(pattern, text, re.IGNORECASE):
                    return await self._call_handler(handler, msg, user)

            if self.fallback:
                return await self._call_handler(self.fallback, msg, user)

        def sync_wrapper(msg):
            # Schedule wrapper safely on the main loop
            asyncio.run_coroutine_threadsafe(wrapper(msg), self.loop)

        self.client.onAnyMessage(sync_wrapper)

    async def _call_handler(self, handler, msg, user):
        history = self.memory[user]
        if inspect.iscoroutinefunction(handler):
            return await handler(msg, self.client, history)
        else:
            return handler(msg, self.client, history)

    def on(self, pattern):
        def decorator(fn):
            self.routes.append((pattern, fn))
            return fn
        return decorator

    def set_fallback(self, fn):
        self.fallback = fn