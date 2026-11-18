from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:@127.0.0.1:3306/inventory_group_demo?charset=utf8mb4",
)
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"
CHRONOS_ENABLED = os.getenv("CHRONOS_ENABLED", "false").lower() == "true"
CHRONOS_MODEL = os.getenv("CHRONOS_MODEL", "amazon/chronos-bolt-small")
CHRONOS_DEVICE = os.getenv("CHRONOS_DEVICE", "cpu")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
DISCOUNT_RATE = min(1.0, max(0.0, float(os.getenv("SPECIAL_DISCOUNT_RATE", "0.20"))))
