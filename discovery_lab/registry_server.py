"""A mini Agent Directory (registry).

This is the "marketplace" part of discovery: instead of the master knowing
agent endpoints, it queries a directory that indexes Agent Cards and answers
skill-tag searches. Mirrors the pattern used by Google Cloud Agent Registry
(`list_agents(filter='skills.tags:"..."')`), but runs locally.

Endpoints:
  GET /agents                    -> all registered cards
  GET /agents/search?skill=summarize -> cards whose skills carry the tag
  GET /health                    -> liveness
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Query
from pydantic import BaseModel


class Registry:
    """In-memory directory of agent cards (JSON dicts)."""

    def __init__(self) -> None:
        self._cards: dict[str, dict] = {}
        self._registered_at: dict[str, float] = {}

    def register(self, card: dict) -> None:
        name = card.get("name")
        if not name:
            raise ValueError("card has no name")
        self._cards[name] = card
        self._registered_at[name] = time.time()

    def unregister(self, name: str) -> None:
        self._cards.pop(name, None)
        self._registered_at.pop(name, None)

    def all(self) -> list[dict]:
        return list(self._cards.values())

    def skills(self) -> dict[str, list[str]]:
        """tag -> [agent names] index built from card skill tags."""
        index: dict[str, list[str]] = {}
        for name, card in self._cards.items():
            for skill in card.get("skills", []):
                for tag in skill.get("tags", []):
                    index.setdefault(tag, []).append(name)
        return index

    def search(self, tag: str) -> list[dict]:
        idx = self.skills().get(tag, [])
        return [self._cards[n] for n in idx]


def _card_json(card: dict) -> dict:
    """Normalise a proto-derived card dict into a slim public shape."""
    return {
        "name": card.get("name"),
        "description": card.get("description"),
        "version": card.get("version"),
        "url": card.get("supportedInterfaces", [{}])[0].get("url")
        or card.get("supported_interfaces", [{}])[0].get("url"),
        "skills": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "description": s.get("description"),
                "tags": s.get("tags", []),
            }
            for s in card.get("skills", [])
        ],
    }


def build_registry_app(registry: Registry | None = None) -> FastAPI:
    registry = registry or Registry()
    app = FastAPI(title="Agent Directory")
    app.state.registry = registry

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "agents": len(registry.all())}

    @app.get("/agents")
    async def list_agents() -> dict:
        return {"agents": [_card_json(c) for c in registry.all()]}

    @app.get("/agents/search")
    async def search_agents(skill: str = Query(..., description="skill tag")) -> dict:
        found = registry.search(skill)
        return {"query": skill, "count": len(found), "agents": [_card_json(c) for c in found]}

    return app