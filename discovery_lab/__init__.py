"""discovery_lab — study how a Master agent efficiently discovers sub-agents over A2A.

Everything runs locally with no cloud account and no paid API key.
Sub-agents are deterministic skill workers; the master uses pluggable
discovery strategies; the free-LLM strategy optionally uses Ollama
(or any OpenAI-compatible endpoint) and falls back to a mock scorer.
"""

__version__ = "0.1.0"