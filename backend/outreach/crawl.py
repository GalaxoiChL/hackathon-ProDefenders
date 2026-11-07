"""Reads a business's own website (respecting robots.txt) for a public contact email and a short
description. At most 3 pages per site: home + up to 2 contact/about pages."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from .http import Http

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
CONTACT_RE = re.compile(r"contact|kontakt|contatt|contato|contacto|impressum|about|despre|über|ueber|"
                        r"a-propos|chi-siamo|quienes|o-nas|om-oss|over-ons|σχετικ|επικοινων|お問い合わせ|会社概要",
                        re.I)
ROLE_PREFIXES = ("info", "contact", "hello", "office", "kontakt", "marketing", "sales", "bonjour", "ciao",
                 "hola", "hallo", "welcome", "reservations", "booking", "events", "biuro", "post", "geral")
JUNK_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|example\.|sentry|wixpress|domain\.com|"
                        r"yourdomain|email\.com|@2x", re.I)


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.text, self.links, self.mailtos = "", "", [], [], []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or a.get("property") or "").lower() in (
                "description", "og:description"):
            self.meta = self.meta or (a.get("content") or "")
        elif tag == "a" and a.get("href"):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                self.mailtos.append(href[7:].split("?")[0])
            else:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.text.append(data.strip())


def parse(html: str) -> _Page:
    p = _Page()
    try:
        p.feed(html)
    except Exception:
        pass
    return p


def extract_emails(page: _Page, raw: str) -> list[str]:
    deobf = re.sub(r"\s*[\[(]\s*(at|@)\s*[\])]\s*", "@", raw, flags=re.I)
    deobf = re.sub(r"\s*[\[(]\s*(dot|\.)\s*[\])]\s*", ".", deobf, flags=re.I)
    found = [e.strip().strip(".") for e in page.mailtos] + EMAIL_RE.findall(deobf)
    out = []
    for e in found:
        e = e.lower()
        if EMAIL_RE.fullmatch(e) and not JUNK_EMAIL.search(e) and e not in out:
            out.append(e)
    return out


def best_email(emails: list[str], site: str | None) -> str | None:
    """Prefer an address on the business's own domain, then role addresses (info@, contact@ ...)."""
    if not emails:
        return None
    domain = urlparse(site or "").netloc.lower().removeprefix("www.")

    def score(e: str) -> tuple:
        local, _, host = e.partition("@")
        return (bool(domain) and host.endswith(domain), local.startswith(ROLE_PREFIXES))

    return max(emails, key=score)


class Crawler:
    def __init__(self, http: Http, user_agent: str):
        self.http = http
        self.ua = user_agent

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        robots = f"{p.scheme}://{p.netloc}/robots.txt"
        rp = RobotFileParser()
        try:
            _, text = self.http.get_text(robots, max_bytes=200_000)
        except Exception:
            return True  # no robots.txt -> allowed
        rp.parse(text.splitlines())
        return rp.can_fetch(self.ua, url)

    def enrich(self, website: str) -> dict:
        """{'email', 'emails', 'description', 'pages'}; never raises."""
        result = {"email": None, "emails": [], "description": None, "pages": []}
        if not website or not self.allowed(website):
            result["blocked"] = bool(website)
            return result
        queue, seen, texts = [website], set(), []
        home_host = urlparse(website).netloc
        while queue and len(result["pages"]) < 3:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                final, html = self.http.get_text(url)
            except Exception:
                continue
            page = parse(html)
            result["pages"].append(final)
            for e in extract_emails(page, html):
                if e not in result["emails"]:
                    result["emails"].append(e)
            if len(result["pages"]) == 1:
                result["description"] = (page.meta or page.title or "").strip()[:400] or None
                for href in page.links:
                    absu = urljoin(final, href)
                    if urlparse(absu).netloc == home_host and CONTACT_RE.search(href) and absu not in queue:
                        if self.allowed(absu):
                            queue.append(absu)
                        if len(queue) >= 2:
                            break
            texts.append(" ".join(page.text)[:1500])
        result["email"] = best_email(result["emails"], website)
        result["text"] = " ".join(texts)[:3000]
        return result
