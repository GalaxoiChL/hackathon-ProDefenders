"""Writes the invitation email (AI, in the market's language) and delivers it.

Safety rails, enforced in code (not left to the AI):
- nothing leaves the machine unless OUTREACH_SEND_ENABLED=true; otherwise .eml files go to output/outbox/
- only emails a human approved are sent
- OUTREACH_TEST_RECIPIENT redirects every email to one inbox (for the demo)
- suppression list (unsubscribe link in every email + List-Unsubscribe header), daily limit
- fixed footer: who we are, why they got it, how to opt out
"""
from __future__ import annotations

import re
import smtplib
import time
from email import policy
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .. import regions
from .config import OutreachSettings
from .db import DB
from .llm import LLM

LINK = "{BID_LINK}"

TEMPLATES = {
    "en": ("{brand}, your ad on a billboard inside a video watched in {market}",
           "Hello {brand} team,\n\nWe place local ads on real billboards that appear inside videos (vlogs, "
           "street footage, streams), shown only to viewers in {market}. Our AI picked your business as a "
           "good fit for a clip of {scene}.\n\nThe placement reaches about {views} viewers in {market}. "
           "Bidding starts at ${floor}, and the highest bid wins the spot.\n\nPlace your bid here: {link}\n\n"
           "Best regards,\n{sender}"),
    "ro": ("{brand}, reclama ta pe un panou dintr-un videoclip văzut în {market}",
           "Bună ziua, echipa {brand},\n\nPunem reclame locale pe panouri reale care apar în videoclipuri "
           "(vloguri, filmări pe stradă, streamuri), afișate doar celor care privesc din {market}. AI-ul nostru "
           "a ales afacerea voastră pentru un clip cu {scene}.\n\nPlasarea ajunge la aproximativ {views} de "
           "privitori din {market}. Licitația pornește de la ${floor}, iar cea mai mare ofertă câștigă locul."
           "\n\nTrimiteți oferta aici: {link}\n\nCu stimă,\n{sender}"),
}

# scene.json is written in English; the Romanian template needs the common phrases translated
SCENE_RO = {"a busy city street": "o stradă aglomerată din oraș", "urban street": "o stradă din oraș"}

FOOTER = ("\n\n--\n{company}, {address}\n"
          "You received this one-time business invitation because {brand} lists this address publicly as "
          "its contact ({source}). We will not write again unless you reply.\n"
          "Unsubscribe: {unsub}")


def _fill(text: str, **kw) -> str:
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text


class Mailer:
    def __init__(self, s: OutreachSettings, db: DB, llm: LLM):
        self.s, self.db, self.llm = s, db, llm

    # ---------- compose ----------
    def compose(self, lead: dict, market: str, scene: str, floor: float, views: int) -> dict:
        c = regions.get(market) or {}
        lang = c.get("language") or "en"
        market_name_en = c.get("name_en", market)
        ro = lang == "ro"
        ctx = dict(brand=lead["name"], market=c.get("name", market) if ro else market_name_en,
                   scene=SCENE_RO.get(scene, scene) if ro else scene, floor=f"{floor:.0f}",
                   views=f"{views:,}".replace(",", ".") if ro else f"{views:,}",
                   sender=self.s.sender_name, link=LINK)
        ai = self.llm.json(
            "You write short, honest B2B emails. Write an invitation email in the language with ISO code "
            f"'{lang}' to the business below. Reply ONLY with JSON {{\"subject\": str, \"body\": str}}.\n"
            f"Business: {lead['name']} ({lead.get('category') or 'local business'}) in {lead.get('city')}, "
            f"{market_name_en}. About them: {(lead.get('description') or '')[:400]}\n"
            f"Offer: their ad on a real billboard that appears inside a video ({scene}), shown only to "
            f"viewers in {market_name_en}; about {views} viewers; bidding starts at ${floor:.0f}; highest bid "
            f"wins. Why them: {lead.get('fit_reason') or ''}\n"
            f"Rules: max 120 words, friendly, no invented facts or statistics, no pressure, include the exact "
            f"text {LINK} where the bid link goes, sign as {self.s.sender_name}. No footer."
        )
        if ai and isinstance(ai.get("subject"), str) and isinstance(ai.get("body"), str) and ai["body"].strip():
            subject, body, used = ai["subject"].strip()[:150], ai["body"].strip(), "ollama"
        else:
            tpl = TEMPLATES.get(lang, TEMPLATES["en"])
            subject, body, used = _fill(tpl[0], **ctx), _fill(tpl[1], **ctx), "rules"
            lang = lang if lang in TEMPLATES else "en"
        if LINK not in body:
            body += f"\n\n{LINK}"
        return {"subject": subject, "body": body, "language": lang, "ai": used}

    def finalize(self, body: str, lead: dict, bid_link: str, unsub_link: str) -> str:
        """Insert the real link and the fixed compliance footer."""
        source = "on its website" if lead.get("email_source") == "website" else "in OpenStreetMap"
        return body.replace(LINK, bid_link) + _fill(
            FOOTER, company=self.s.sender_company, address=self.s.sender_address, brand=lead["name"],
            source=source, unsub=unsub_link)

    # ---------- deliver ----------
    def _message(self, email: dict, to_addr: str, unsub: str) -> EmailMessage:
        # long lines allowed (RFC 5322 limit): otherwise the long List-Unsubscribe URL gets
        # RFC 2047-encoded and mail clients no longer recognise it
        msg = EmailMessage(policy=policy.SMTP.clone(max_line_length=998))
        msg["From"] = formataddr((self.s.sender_name, self.s.smtp_from or "outreach@localhost"))
        msg["To"] = to_addr
        msg["Subject"] = email["subject"]
        msg["Message-ID"] = make_msgid(domain="prodefenders.local")
        msg["List-Unsubscribe"] = f"<{unsub}>"
        if to_addr != email["to_addr"]:
            msg["X-Original-To"] = email["to_addr"]
        msg.set_content(email["body"])
        return msg

    def deliver(self, email: dict, unsub: str) -> dict:
        """Send one approved email (or write it to the outbox). Returns the updated fields."""
        if self.db.suppressed(email["to_addr"]):
            return {"status": "skipped", "error": "recipient unsubscribed"}
        to_addr = self.s.test_recipient or email["to_addr"]
        msg = self._message(email, to_addr, unsub)
        self.s.outbox_dir.mkdir(parents=True, exist_ok=True)
        path = self.s.outbox_dir / f"email_{email['id']:05d}.eml"
        path.write_bytes(bytes(msg))
        if not self.s.send_enabled:
            return {"status": "outbox", "outbox_path": str(path), "error": None}
        if self.db.sent_today() >= self.s.daily_limit:
            return {"status": "approved", "error": f"daily limit of {self.s.daily_limit} reached, retry tomorrow"}
        if not self.s.smtp_host:
            return {"status": "failed", "error": "SMTP_HOST is not configured"}
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(msg)
        except Exception as e:
            return {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        return {"status": "sent", "sent": time.time(), "outbox_path": str(path), "error": None}


def looks_personal(email: str) -> bool:
    """firstname.lastname@ style addresses are personal data under GDPR: we skip them by default."""
    local = email.split("@")[0]
    return bool(re.fullmatch(r"[a-z]+[._-][a-z]+", local)) and not local.startswith(
        ("info", "contact", "office", "hello", "sales", "marketing"))
