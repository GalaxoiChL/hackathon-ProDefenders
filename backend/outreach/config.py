"""Outreach settings. Sending real email is OFF unless explicitly enabled."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import ROOT, _bool, load_dotenv

# Where to look for businesses in each demo market when no city is given
MARKET_CITIES = {
    "US": "New York", "RO": "București", "JP": "Tokyo", "GB": "London", "DE": "Berlin",
    "FR": "Paris", "IT": "Roma", "ES": "Madrid", "NL": "Amsterdam", "BE": "Bruxelles",
    "PL": "Warszawa", "SE": "Stockholm", "AT": "Wien", "PT": "Lisboa", "GR": "Αθήνα",
}


@dataclass(frozen=True)
class OutreachSettings:
    db_path: Path = ROOT / "output" / "outreach.db"
    outbox_dir: Path = ROOT / "output" / "outbox"
    public_base_url: str = "http://localhost:8000"     # used in bid / unsubscribe links
    secret_key: str = ""                               # signs bid links; generated + stored if empty
    # sender identity (shown in every email; required by CAN-SPAM / EU e-commerce rules)
    sender_name: str = "Swapboard"
    sender_company: str = "Swapboard (ITFest 2026 demo)"
    sender_address: str = "București, România"
    # AI
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ai_enabled: bool = True
    # search
    brave_api_key: str = ""
    user_agent: str = "Swapboard-hackathon/1.0 (+https://github.com/GalaxoiChL/hackathon-ProDefenders)"
    http_timeout: float = 8.0
    # sending
    send_enabled: bool = False                         # master switch: False = drafts + outbox only
    test_recipient: str = ""                           # if set, EVERY email goes here instead
    daily_limit: int = 20
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @classmethod
    def from_env(cls, root: Path = ROOT) -> "OutreachSettings":
        load_dotenv(root / ".env")
        e = os.environ
        return cls(
            db_path=root / "output" / "outreach.db",
            outbox_dir=root / "output" / "outbox",
            public_base_url=e.get("PUBLIC_BASE_URL", cls.public_base_url).rstrip("/"),
            secret_key=e.get("SECRET_KEY", ""),
            sender_name=e.get("OUTREACH_SENDER_NAME", cls.sender_name),
            sender_company=e.get("OUTREACH_SENDER_COMPANY", cls.sender_company),
            sender_address=e.get("OUTREACH_SENDER_ADDRESS", cls.sender_address),
            ollama_url=e.get("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            ollama_model=e.get("OLLAMA_MODEL", cls.ollama_model),
            ai_enabled=_bool(e.get("AI_ENABLED"), True),
            brave_api_key=e.get("BRAVE_API_KEY", ""),
            send_enabled=_bool(e.get("OUTREACH_SEND_ENABLED"), False),
            test_recipient=e.get("OUTREACH_TEST_RECIPIENT", ""),
            daily_limit=int(e.get("OUTREACH_DAILY_LIMIT", cls.daily_limit)),
            smtp_host=e.get("SMTP_HOST", ""),
            smtp_port=int(e.get("SMTP_PORT", cls.smtp_port)),
            smtp_user=e.get("SMTP_USER", ""),
            smtp_password=e.get("SMTP_PASSWORD", ""),
            smtp_from=e.get("SMTP_FROM", "") or e.get("SMTP_USER", ""),
        )
