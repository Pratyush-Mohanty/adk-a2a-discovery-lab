"""Thin async helpers for the two things a Master needs over A2A:

  1. discover  -> fetch an Agent Card  (A2ACardResolver)
  2. route     -> send a message/task  (Client.send_message)
"""

from __future__ import annotations

import json
import logging
import time
import uuid

import httpx
from a2a.client import A2ACardResolver, create_client
from a2a.helpers import get_stream_response_text
from a2a.types import Message, Part, Role, SendMessageRequest

from .config import HTTP_TIMEOUT_S

logger = logging.getLogger("discovery_lab.client")


async def fetch_card(base_url: str, *, timeout: float = HTTP_TIMEOUT_S) -> dict:
    """Fetch and return an agent's Agent Card as a JSON dict."""
    async with httpx.AsyncClient(timeout=timeout) as hc:
        resolver = A2ACardResolver(httpx_client=hc, base_url=base_url.rstrip("/"))
        card = await resolver.get_agent_card()
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(card, preserving_proto_field_name=False)


async def send_text(
    agent_base_url: str, text: str, *, timeout: float = HTTP_TIMEOUT_S
) -> tuple[str, float]:
    """Send a user message to a remote A2A agent; return (reply_text, elapsed_s).

    `agent_base_url` is the agent's root (e.g. http://host:8101/). The client
    resolves the Agent Card itself, then routes via message/send.
    """
    start = time.perf_counter()
    client = await create_client(agent=agent_base_url.rstrip("/") + "/")
    try:
        request = SendMessageRequest(
            message=Message(
                message_id=str(uuid.uuid4()),
                role=Role.ROLE_USER,
                parts=[Part(text=text)],
            )
        )
        chunks: list[str] = []
        async for response in client.send_message(request):
            text_piece = get_stream_response_text(response)
            if text_piece:
                chunks.append(text_piece)
        elapsed = time.perf_counter() - start
        return ("\n".join(chunks), elapsed)
    finally:
        await client.close()


async def check_health(base_url: str, *, timeout: float = 3.0) -> bool:
    """Probe whether an HTTP server is up at base_url (any response = alive)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as hc:
            r = await hc.get(base_url.rstrip("/") + "/")
            return r.status_code < 500
    except Exception:
        return False