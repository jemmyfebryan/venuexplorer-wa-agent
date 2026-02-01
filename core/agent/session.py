"""
handler.py

Conversation handler, session manager and sqlite session DB for WhatsApp bot.

Drop this file into: ./src/orin_wa_report/core/agent/handler.py

What it provides
- chat_response(msg, client, history): async function that handles incoming conversation messages
  (creates/updates session, stores message, generates a placeholder reply based on history, sends the reply
   and stores the bot reply in DB).
- register_conv_handler(bot): convenience function to register the r"^conv" handler on your ChatBotHandler
- handler_verify_wa(...) : a small placeholder kept to preserve existing import from main.py. Replace with your
  real verification logic if you have one.

DB location (auto-created): ./src/orin_wa_report/core/database/chat_sessions.db

Design notes
- sessions table: one row per session (session = conversation between bot and single phone) -- scalable. 
- messages table: one row per chat bubble (user or bot), linked to sessions by session_id.
- Session lifecycle: session starts on first user message, inactivity end after 15 minutes (with 5-min warning at 10m),
  forced end after 2 hours (with 5-min warning at 1h55m). Both warnings are sent to the user. 

This file tries to avoid external dependencies (uses builtin sqlite3). It serializes DB operations using a small
asyncio.Lock + run_in_executor to avoid blocking the event loop.

If you want a production setup: migrate to Postgres+async driver or a dedicated session service; for contextual
responses integrate a small LLM or vector DB using the messages history.

"""

import json
import asyncio
import os
import sqlite3
import time
import uuid
import json
import re
import httpx
from openai import OpenAI
from pathlib import Path
from typing import Optional, Dict, Any, List


import copy
from core.agent.handler import (
    get_venue_recommendation,
    book_venue,
    book_now
)
from core.agent.llm import (
    get_question_class,
    get_venue_summary,
    get_venue_conclusion,
    get_confirm_booking,
    get_final_response,
    extract_user_requirements,
)
from core.agent.config import (
    INACTIVITY_END_SECONDS,
    INACTIVITY_WARNING_SECONDS,
    FORCED_SESSION_SECONDS,
    FORCED_WARNING_BEFORE,
    question_class_details,
    AGENT_ERROR_DEFAULT_MESSAGE,
    AGENT_SESSION_WARNING_MESSAGE,
    AGENT_SESSION_END_MESSAGE,
    AGENT_SESSION_LIMIT_MESSAGE,
)

from core.agent.prompts import (
    GENERAL_TALK_EXTRA_PROMPT,
    VENUE_RECOMMENDATION_EXTRA_PROMPT,
    CONFIRM_BOOKING_EXTRA_PROMPT,
)

from core.logger import get_logger

logger = get_logger(__name__, service="Agent")

from dotenv import load_dotenv
load_dotenv(override=True)


# -----------------------------
# Configuration / constants
# -----------------------------
CORE_DIR = Path(__file__).resolve().parents[1]  # core/
DB_DIR = CORE_DIR / "database"
DB_PATH = DB_DIR / "chat_sessions.db"

# -----------------------------
# Lightweight sqlite wrapper
# -----------------------------

class ChatDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_done = False
        # small in-process sqlite is protected by an asyncio lock and run_in_executor for blocking ops
        self._lock = asyncio.Lock()

    async def initialize(self):
        async with self._lock:
            if self._init_done:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # connect
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            # safer WAL mode for concurrent readers/writers
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            await asyncio.get_running_loop().run_in_executor(None, self._create_tables)
            self._init_done = True
            logger.info(f"ChatDB initialized at {self.db_path}")

    def _create_tables(self):
        c = self._conn.cursor()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                user_name TEXT,
                started_at INTEGER NOT NULL,
                last_activity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                ended_at INTEGER,
                metadata TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_phone ON sessions(phone);
            CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity);

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                body TEXT,
                timestamp INTEGER NOT NULL,
                metadata TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_ts ON messages(session_id, timestamp);
            
            -- NEW TABLE FOR USER REQUIREMENTS
            CREATE TABLE IF NOT EXISTS user_requirements (
                session_id TEXT NOT NULL,
                event_type TEXT,
                location TEXT,
                attendees INTEGER,
                budget TEXT,
                start_date TEXT,
                end_date TEXT,
                email TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            """
        )
        self._conn.commit()

    async def _run(self, fn, *args, **kwargs):
        """Run a blocking DB call in executor with lock."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # --- session operations ---
    async def create_session(self, phone: str, user_name: str, started_at: Optional[int] = None) -> str:
        if started_at is None:
            started_at = int(time.time())
        session_id = uuid.uuid4().hex
        def _create():
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO sessions (id, phone, user_name, started_at, last_activity, status) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, phone, user_name, started_at, started_at, 'active')
            )
            self._conn.commit()
            return session_id
        return await self._run(_create)

    async def update_session_activity(self, session_id: str, last_activity: Optional[int] = None):
        if last_activity is None:
            last_activity = int(time.time())
        def _update():
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE sessions SET last_activity = ? WHERE id = ?",
                (last_activity, session_id)
            )
            self._conn.commit()
        await self._run(_update)

    async def end_session(self, session_id: str, ended_at: Optional[int] = None, status: str = "ended"):
        if ended_at is None:
            ended_at = int(time.time())
        def _end():
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
                (status, ended_at, session_id)
            )
            self._conn.commit()
        await self._run(_end)

    async def get_session_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        def _get():
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, phone, user_name, started_at, last_activity, status, ended_at FROM sessions WHERE phone = ? ORDER BY started_at DESC LIMIT 1",
                (phone,)
            )
            row = cur.fetchone()
            if not row:
                return None
            keys = ["id","phone","user_name","started_at","last_activity","status","ended_at"]
            return dict(zip(keys, row))
        return await self._run(_get)

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, phone, user_name, started_at, last_activity, status, ended_at FROM sessions WHERE id = ?",
                (session_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            keys = ["id","phone","user_name","started_at","last_activity","status","ended_at"]
            return dict(zip(keys, row))
        return await self._run(_get)

    # --- messages ---
    async def add_message(self, session_id: str, sender: str, body: str, timestamp: Optional[int] = None, metadata: Optional[dict] = None) -> str:
        if timestamp is None:
            timestamp = int(time.time())
        if metadata is None:
            metadata = {}
        message_id = uuid.uuid4().hex
        def _add():
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO messages (id, session_id, sender, body, timestamp, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, session_id, sender, body, timestamp, json.dumps(metadata))
            )
            self._conn.commit()
            return message_id
        return await self._run(_add)

    async def get_messages_for_session(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        def _get():
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, sender, body, timestamp, metadata FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cur.fetchall()
            out = []
            for r in rows:
                out.append({
                    "id": r[0],
                    "sender": r[1],
                    "body": r[2],
                    "timestamp": r[3],
                    "metadata": json.loads(r[4]) if r[4] else None
                })
            return out
        return await self._run(_get)
        
    # --- user requirements ---
    async def get_user_requirements(self, session_id: str) -> Dict[str, Any]:
        def _get():
            cur = self._conn.cursor()
            cur.execute(
                "SELECT event_type, location, attendees, budget, start_date, end_date, email FROM user_requirements WHERE session_id = ?",
                (session_id,)
            )
            row = cur.fetchone()
            if not row:
                return {}
            keys = ["event_type", "location", "attendees", "budget", "start_date", "end_date", "email"]
            return dict(zip(keys, row))
        return await self._run(_get)

    async def update_user_requirements(self, session_id: str, requirements: Dict[str, Any]):
        def _upsert():
            cur = self._conn.cursor()
            # Check if record exists
            cur.execute("SELECT 1 FROM user_requirements WHERE session_id = ?", (session_id,))
            exists = cur.fetchone()
            
            if exists:
                # Update existing
                cur.execute(
                    """UPDATE user_requirements SET
                    event_type = COALESCE(?, event_type),
                    location = COALESCE(?, location),
                    attendees = COALESCE(?, attendees),
                    budget = COALESCE(?, budget),
                    start_date = COALESCE(?, start_date),
                    end_date = COALESCE(?, end_date),
                    email = COALESCE(?, email)
                    WHERE session_id = ?""",
                    (
                        requirements.get("event_type"),
                        requirements.get("location"),
                        requirements.get("attendees"),
                        requirements.get("budget"),
                        requirements.get("start_date"),
                        requirements.get("end_date"),
                        requirements.get("email"),
                        session_id
                    )
                )
            else:
                # Insert new
                cur.execute(
                    """INSERT INTO user_requirements
                    (session_id, event_type, location, attendees, budget, start_date, end_date, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        requirements.get("event_type"),
                        requirements.get("location"),
                        requirements.get("attendees"),
                        requirements.get("budget"),
                        requirements.get("start_date"),
                        requirements.get("end_date"),
                        requirements.get("email")
                    )
                )
            self._conn.commit()
        await self._run(_upsert)

# -----------------------------
# Session manager in memory
# -----------------------------

class SessionEntry:
    def __init__(self, session_id: str, phone: str, jid: str, user_name: str, started_at: int, last_activity: int):
        self.session_id = session_id
        self.phone = phone
        self.jid = jid  # full whatsapp jid '6281...@s.whatsapp.net'
        self.user_name = user_name
        self.started_at = started_at
        self.last_activity = last_activity
        self.inactivity_task: Optional[asyncio.Task] = None
        self.forced_task: Optional[asyncio.Task] = None


class SessionManager:
    def __init__(self, db: ChatDB):
        self.db = db
        self._sessions: Dict[str, SessionEntry] = {}  # key by phone
        self._lock = asyncio.Lock()

    async def ensure_session(self, phone: str, jid: str, user_name: str, client) -> SessionEntry:
        """Get existing active session for phone or create a new one."""
        now = int(time.time())
        async with self._lock:
            entry = self._sessions.get(phone)
            if entry:
                # verify it's still active in DB
                sess = await self.db.get_session(entry.session_id)
                if sess and sess.get("status") == "active":
                    # update last_activity in db + in-memory
                    await self.db.update_session_activity(entry.session_id, now)
                    entry.last_activity = now
                    # reset inactivity watcher
                    if entry.inactivity_task:
                        entry.inactivity_task.cancel()
                    entry.inactivity_task = asyncio.create_task(self._inactivity_watcher(entry, client))
                    return entry
                else:
                    # stale entry in memory
                    await self._cancel_tasks(entry)
                    self._sessions.pop(phone, None)

            # look in DB for most recent session for this phone
            dbsess = await self.db.get_session_by_phone(phone)
            if dbsess and dbsess.get("status") == "active":
                # check started_at + FORCED_SESSION_SECONDS
                if int(time.time()) - int(dbsess.get("started_at")) < FORCED_SESSION_SECONDS:
                    # reuse
                    entry = SessionEntry(
                        session_id=dbsess["id"],
                        phone=phone,
                        jid=jid,
                        user_name=dbsess.get("user_name") or user_name,
                        started_at=int(dbsess.get("started_at")),
                        last_activity=int(dbsess.get("last_activity"))
                    )
                    # schedule watchers
                    entry.inactivity_task = asyncio.create_task(self._inactivity_watcher(entry, client))
                    entry.forced_task = asyncio.create_task(self._forced_watcher(entry, client))
                    self._sessions[phone] = entry
                    await self.db.update_session_activity(entry.session_id, now)
                    entry.last_activity = now
                    return entry
                else:
                    # session too old - end it in DB and create new
                    try:
                        await self.db.end_session(dbsess["id"], ended_at=int(time.time()), status="ended")
                    except Exception:
                        logger.exception("Failed to mark old session ended")

            # create new session
            session_id = await self.db.create_session(phone, user_name, started_at=now)
            entry = SessionEntry(session_id=session_id, phone=phone, jid=jid, user_name=user_name, started_at=now, last_activity=now)
            entry.inactivity_task = asyncio.create_task(self._inactivity_watcher(entry, client))
            entry.forced_task = asyncio.create_task(self._forced_watcher(entry, client))
            self._sessions[phone] = entry
            logger.info(f"Created new session {session_id} for {phone}")
            return entry

    async def touch_session(self, phone: str, client):
        """Update session last_activity and restart inactivity watcher."""
        async with self._lock:
            entry = self._sessions.get(phone)
            if not entry:
                return None
            now = int(time.time())
            entry.last_activity = now
            try:
                await self.db.update_session_activity(entry.session_id, now)
            except Exception:
                logger.exception("Failed to update session activity")
            if entry.inactivity_task:
                entry.inactivity_task.cancel()
            entry.inactivity_task = asyncio.create_task(self._inactivity_watcher(entry, client))
            return entry

    async def _cancel_tasks(self, entry: SessionEntry):
        if entry.inactivity_task:
            try:
                entry.inactivity_task.cancel()
            except Exception:
                pass
        if entry.forced_task:
            try:
                entry.forced_task.cancel()
            except Exception:
                pass

    async def _inactivity_watcher(self, entry: SessionEntry, client):
        """Sends a 5-min warning at 10 minutes of inactivity then ends the session at 15 minutes if no reply."""
        try:
            # sleep until warning
            await asyncio.sleep(INACTIVITY_WARNING_SECONDS)
            # check actual last_activity
            sess = await self.db.get_session(entry.session_id)
            if not sess or sess.get("status") != "active":
                return
            last_activity = int(sess.get("last_activity"))
            now = int(time.time())
            if now - last_activity < INACTIVITY_WARNING_SECONDS:
                # activity happened - watcher will be restarted by touch_session
                return
            # send warning
            warn_text = AGENT_SESSION_WARNING_MESSAGE
            try:
                client.sendText(entry.jid, warn_text)
            except Exception:
                logger.exception("Failed to send inactivity warning")
            # wait final 5 minutes
            await asyncio.sleep(INACTIVITY_END_SECONDS - INACTIVITY_WARNING_SECONDS)
            # final check
            sess = await self.db.get_session(entry.session_id)
            if not sess or sess.get("status") != "active":
                return
            last_activity = int(sess.get("last_activity"))
            now = int(time.time())
            if now - last_activity < INACTIVITY_END_SECONDS:
                # user replied in the meantime
                return
            # end session
            logger.info(f"Ending session {entry.session_id} for {entry.phone} due to inactivity")
            try:
                client.sendText(entry.jid, AGENT_SESSION_END_MESSAGE)
            except Exception:
                logger.exception("Failed to send inactivity final message")
            await self.db.end_session(entry.session_id, ended_at=int(time.time()), status="ended")
            # cleanup
            async with self._lock:
                await self._cancel_tasks(entry)
                self._sessions.pop(entry.phone, None)
        except asyncio.CancelledError:
            # watcher cancelled because of new activity / session end
            return
        except Exception:
            logger.exception("Error in inactivity watcher for session %s", entry.session_id)

    async def _forced_watcher(self, entry: SessionEntry, client):
        """Force-end long sessions after FORCED_SESSION_SECONDS. Send a 5-minute warning beforehand."""
        try:
            total = FORCED_SESSION_SECONDS
            warn_at = total - FORCED_WARNING_BEFORE
            await asyncio.sleep(warn_at)
            # double-check session still active
            sess = await self.db.get_session(entry.session_id)
            if not sess or sess.get("status") != "active":
                return
            try:
                client.sendText(entry.jid, AGENT_SESSION_LIMIT_MESSAGE)
            except Exception:
                logger.exception("Failed to send forced-end warning")
            await asyncio.sleep(FORCED_WARNING_BEFORE)
            # final end
            sess = await self.db.get_session(entry.session_id)
            if not sess or sess.get("status") != "active":
                return
            logger.info(f"Force ending session {entry.session_id} for {entry.phone} due to time limit")
            try:
                client.sendText(entry.jid, AGENT_SESSION_END_MESSAGE)
            except Exception:
                logger.exception("Failed to send forced final message")
            await self.db.end_session(entry.session_id, ended_at=int(time.time()), status="ended")
            async with self._lock:
                await self._cancel_tasks(entry)
                self._sessions.pop(entry.phone, None)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Error in forced watcher for session %s", entry.session_id)
            
    async def end_session(self, phone: str, client, reason: str = "ended"):
        """Manually end a user session."""
        async with self._lock:
            entry = self._sessions.get(phone)
            if not entry:
                return False
            try:
                await self.db.end_session(entry.session_id, ended_at=int(time.time()), status=reason)
            except Exception:
                logger.exception("Failed to end session in DB")
                return False
            try:
                client.sendText(entry.jid, AGENT_SESSION_END_MESSAGE)
            except Exception:
                logger.exception("Failed to send session end message")
            await self._cancel_tasks(entry)
            self._sessions.pop(phone, None)
            logger.info(f"Session {entry.session_id} for {phone} ended manually with reason: {reason}")
            return True


# -----------------------------
# Module-level singletons
# -----------------------------
_DB: Optional[ChatDB] = None
_SESSION_MANAGER: Optional[SessionManager] = None
_db_init_lock = asyncio.Lock()

async def _ensure_db_and_manager():
    global _DB, _SESSION_MANAGER
    async with _db_init_lock:
        if _DB is None:
            _DB = ChatDB(DB_PATH)
            await _DB.initialize()
            _SESSION_MANAGER = SessionManager(_DB)

# -----------------------------
# Chat response logic
# -----------------------------

GREETINGS = re.compile(r"\b(hi|hello|hai|halo|hey)\b", re.I)
GOODBYES = re.compile(r"\b(bye|goodbye|terima kasih|thanks|thx)\b", re.I)

def markdown_to_whatsapp(text: str) -> str:
    # Bold: **text** → *text*
    text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

    # Italic: _text_ or *text* → _text_
    # (Markdown often uses *italic* as well)
    text = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?<!\*)", r"_\1_", text)
    text = re.sub(r"_(.*?)_", r"_\1_", text)

    # Strikethrough: ~~text~~ → ~text~
    text = re.sub(r"~~(.*?)~~", r"~\1~", text)

    # Inline code: `text` → ```text```
    text = re.sub(r"`(.*?)`", r"```\1```", text)

    # Remove Markdown headers (#, ##, ### etc.)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

    return text

async def chat_response(
    msg: Dict[str, Any],
    client,
    openai_client: OpenAI,
    history=None
) -> str:
    """
    Main entrypoint to handle a conversational message. This function:
      - ensures DB and session manager exist
      - finds/creates a session for the caller
      - saves the incoming user message to messages table
      - builds a simple reply using session history (placeholder logic)
      - sends the reply via client.sendText and stores the bot reply

    Parameters:
        msg: the incoming message object from wa-automate (same structure as in main.py)
        client: the wa-automate SocketClient instance (used to send replies)
        history: optional, unused (kept for compatibility)

    Returns:
        The reply text that was sent.
    """
    try:
        await _ensure_db_and_manager()
        assert _DB is not None and _SESSION_MANAGER is not None

        # ignore group messages
        if msg.get("data", {}).get("isGroupMsg"):
            return ""

        phone_jid = msg["data"].get("from")
        phone = phone_jid.split("@")[0]
        sender = msg["data"].get("sender", {}) or {}
        user_name = sender.get("pushname", "")
        text = (msg["data"].get("body") or "").strip()

        # ensure session exists
        entry = await _SESSION_MANAGER.ensure_session(phone=phone, jid=phone_jid, user_name=user_name, client=client)

        # store user message and extract requirements
        try:
            await _DB.add_message(entry.session_id, sender="user", body=text)
            
            # Get messages including the new one
            messages = await _DB.get_messages_for_session(entry.session_id, limit=20)
            last_messages = messages[:10]  # Only get 10 last messages for context
            
            # Build LLm messages for requirements extraction
            llm_messages = [
                {
                    "role": "assistant" if m["sender"] == "bot" else "user",
                    "content": m["body"]
                }
                for m in reversed(last_messages)
            ]
            
            # Extract and store user requirements
            requirements = await extract_user_requirements(
                openai_client=openai_client,
                messages=llm_messages
            )
            await _DB.update_user_requirements(entry.session_id, requirements)
            
        except Exception:
            logger.exception("Failed to store message or extract requirements")

        # Build a simple context from last user messages
        messages = await _DB.get_messages_for_session(entry.session_id, limit=20)
        last_messages = messages[:10]
        last_message = messages[0]
        logger.info(f"Get last message: {last_message}")
        
        # Build LLm messages for response generation
        llm_messages = [
            {
                "role": "assistant" if m["sender"] == "bot" else "user",
                "content": m["body"]
            }
            for m in reversed(last_messages)
        ]
        
        logger.info(f"Get First LLM message: {llm_messages[0]}")
        
        # Get stored requirements to guide conversation
        requirements = await _DB.get_user_requirements(entry.session_id)
        logger.info(f"Stored requirements: {requirements}")
        
        question_class_result = await get_question_class(
            openai_client=openai_client,
            messages=llm_messages,
            question_class_details=question_class_details
        )
        question_class_dict = copy.deepcopy(question_class_details)
        for cr in question_class_result:
            question_class_dict = question_class_dict.get(cr)
            if "subclass" in question_class_dict.keys():
                question_class_dict = question_class_dict.get("subclass")
                
        question_class_tools: str = question_class_dict.get("tools")
                
        logger.info(f"Question class dict: {question_class_dict}")
        
        if question_class_tools == "general_talk":
            extra_prompt = GENERAL_TALK_EXTRA_PROMPT
            # Add requirements context to prompt
            if requirements:
                extra_prompt += f"\n\nUser requirements: {requirements}"
                
        elif question_class_tools == "end_session":
            logger.info("User want to end session by chat")
            await _SESSION_MANAGER.end_session(phone=phone, client=client)
            return
        elif question_class_tools == "venue_recommendation":
            venue_summary = await get_venue_summary(
                openai_client=openai_client,
                messages=llm_messages
            )
            
            # Use stored requirements if available
            if requirements:
                stored_requirements = json.dumps(requirements)
                
            venue_summary = f"{venue_summary}. {stored_requirements}"
            
            logger.info(f"Venue Summary: {venue_summary}")
            
            venue_recommendation = await get_venue_recommendation(
                phone_number=phone,
                text_body=venue_summary,
                k_venue=5
            )
            venue_conclusion = await get_venue_conclusion(
                openai_client=openai_client,
                messages=llm_messages,
                venue_recommendation=venue_recommendation
            )
            logger.info(f"Venue Conclusion: {venue_conclusion}")
            extra_prompt = VENUE_RECOMMENDATION_EXTRA_PROMPT.format(
                venue_conclusion=venue_conclusion
            )
        elif question_class_tools == "confirm_booking":
            # Check if we have email in requirements
            email = requirements.get("email", "") if requirements else ""
            customer_name = entry.user_name or ""
            
            # Validate all required fields before booking
            missing_fields = []
            if not email:
                missing_fields.append("email address")
            if not customer_name:
                missing_fields.append("your name")
            
            if missing_fields:
                # Request missing information before proceeding with booking
                missing_str = " and ".join(missing_fields)
                extra_prompt = f"Please provide {missing_str} so we can proceed with the booking confirmation."
                logger.info(f"Missing required fields for booking: {missing_fields}")
            else:
                venue_summary = await get_venue_summary(
                    openai_client=openai_client,
                    messages=llm_messages
                )
                
                # Use stored requirements if available
                if requirements:
                    stored_requirements = json.dumps(requirements)
                    
                venue_summary = f"{venue_summary}. {stored_requirements}"
                    
                logger.info(f"Venue Summary: {venue_summary}")
                
                venue_recommendation = await get_venue_recommendation(
                    phone_number=phone,
                    text_body=venue_summary,
                    k_venue=5
                )
                ticket_id = venue_recommendation.get("ticket_id", "N/A")
                logger.info(f"Ticket ID: {ticket_id}")
                
                confirm_booking_result = await get_confirm_booking(
                    openai_client=openai_client,
                    messages=llm_messages,
                    venue_recommendation=venue_recommendation,
                )
                venue_name = confirm_booking_result.get("venue_name")
                venue_id = confirm_booking_result.get("venue_id")
                
                # Validate venue_id before booking
                if not venue_id:
                    extra_prompt = "I couldn't determine which venue you want to book. Please specify the venue name or number from the recommendations."
                    logger.info("Venue ID not found - requesting user to specify venue")
                else:
                    logger.info(f"Venue Name: {venue_name}, Venue ID: {venue_id}")
                    
                    book_now_text = await book_now(
                        ticket_id=ticket_id,
                        venue_name=venue_name,
                        venue_id=venue_id,
                        email_address=email,
                        customer_name=customer_name
                    )
                    
                    logger.info(f"Confirm Booking: book_now_text: {book_now_text}")
                    
                    extra_prompt = CONFIRM_BOOKING_EXTRA_PROMPT.format(
                        book_venue_text=book_now_text
                    )
        else:
            logger.error(f"Can't find the question_class")
            return
        
        logger.info(f"Extra prompt: {extra_prompt}")
        
        # Final Response
        final_response = await get_final_response(
            openai_client=openai_client,
            messages=llm_messages,
            extra_prompt=extra_prompt,
        )
        
        final_response_header = final_response.get("response_header", "")
        final_response_content = final_response.get("response_content", "")
        final_response_footer = final_response.get("response_footer", "")

        # Keep only non-empty parts
        parts = [final_response_header, final_response_content, final_response_footer]
        final_response_str = "\n\n".join(part for part in parts if part.strip())
        
        logger.info(f"Final Response: {final_response_str}")
        # Parse from Marksdown style to Whatsapp style
        final_response_str = markdown_to_whatsapp(final_response_str)
        
        if not final_response_str:
            final_response_str = AGENT_ERROR_DEFAULT_MESSAGE
    except Exception as e:
        logger.exception("Error in response chat (type=%s): %r", type(e).__name__, e)
        final_response_str = AGENT_ERROR_DEFAULT_MESSAGE


    # send the reply
    try:
        await client.sendText(phone_jid, final_response_str)
    except Exception:
        logger.exception("Failed to send reply to %s", phone_jid)

    # store bot message
    try:
        await _DB.add_message(entry.session_id, sender="bot", body=final_response_str)
    except Exception:
        logger.exception("Failed to store bot message")

    # update session activity (this will also restart inactivity watcher)
    await _SESSION_MANAGER.touch_session(phone, client)

    return final_response_str
