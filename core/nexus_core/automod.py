"""Motor de AutoMod: funciones puras para que el bot y la API ("probar regla") den el mismo resultado."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

URL_RE = re.compile(r"https?://([^\s/<>]+)", re.I)
INVITE_RE = re.compile(r"(?:discord(?:app)?\.com/invite|discord\.gg)/([a-z0-9-]+)", re.I)
MENTION_RE = re.compile(r"<@[!&]?\d+>")

# Sustituciones típicas para evadir filtros (4 → a, 3 → e, …).
LEET = str.maketrans({"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t"})


@dataclass
class MessageInfo:
    content: str
    mention_count: int = 0
    guild_invite_codes: set[str] = field(default_factory=set)  # invitaciones del propio servidor


@dataclass
class Match:
    reason: str
    detail: str | None = None


def _word_pattern(word: str) -> re.Pattern[str]:
    escaped = re.escape(word).replace(r"\*", r"\w*")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.I)


def check_static(rule_type: str, cfg: dict[str, Any], msg: MessageInfo) -> Match | None:
    """Reglas que solo dependen del mensaje actual."""
    text = msg.content or ""
    if rule_type == "bad_words":
        normalized = text.lower().translate(LEET)
        for w in cfg.get("words", []):
            if _word_pattern(w).search(text) or _word_pattern(w).search(normalized):
                return Match("bad_words", w)
    elif rule_type == "links":
        domains = [d.lower().removeprefix("www.") for d in URL_RE.findall(text)]
        domains = [d.split(":")[0] for d in domains if not INVITE_RE.search(f"https://{d}/x")]
        listed = cfg.get("domains", [])

        def listed_match(d: str) -> bool:
            return any(d == x or d.endswith("." + x) for x in listed)

        for d in domains:
            mode = cfg.get("mode", "allowlist")
            if mode == "block_all" or (mode == "allowlist" and not listed_match(d)) or (
                    mode == "blocklist" and listed_match(d)):
                return Match("links", d)
    elif rule_type == "invites":
        for code in INVITE_RE.findall(text):
            if cfg.get("allow_own_server", True) and code.lower() in {c.lower() for c in msg.guild_invite_codes}:
                continue
            return Match("invites", code)
    elif rule_type == "mass_mentions":
        count = max(msg.mention_count, len(MENTION_RE.findall(text)))
        if count > int(cfg.get("max_mentions", 5)):
            return Match("mass_mentions", str(count))
    elif rule_type == "caps":
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= int(cfg.get("min_length", 10)):
            pct = 100 * sum(c.isupper() for c in letters) / len(letters)
            if pct > int(cfg.get("max_percent", 70)):
                return Match("caps", f"{pct:.0f}%")
    return None


class RateTracker:
    """Ventanas deslizantes en memoria para spam y mensajes repetidos."""

    def __init__(self) -> None:
        self._times: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._texts: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)

    def check(self, rule_type: str, cfg: dict[str, Any], guild_id: int, user_id: int, text: str,
              now: float | None = None) -> Match | None:
        now = time.monotonic() if now is None else now
        key = (guild_id, user_id)
        if rule_type == "spam":
            window = int(cfg.get("per_seconds", 5))
            q = self._times[key]
            q.append(now)
            while q and now - q[0] > window:
                q.popleft()
            if len(q) > int(cfg.get("max_messages", 5)):
                return Match("spam", str(len(q)))
        elif rule_type == "duplicates":
            window = int(cfg.get("per_seconds", 30))
            q2 = self._texts[key]
            norm = " ".join(text.lower().split())
            q2.append((now, norm))
            while q2 and now - q2[0][0] > window:
                q2.popleft()
            repeats = sum(1 for _, t in q2 if t == norm and norm)
            if repeats > int(cfg.get("max_repeats", 3)):
                return Match("duplicates", str(repeats))
        return None

    def prune(self, max_age: float = 600) -> None:
        now = time.monotonic()
        for d in (self._times, self._texts):
            for k in list(d):
                q = d[k]
                last = q[-1] if q else None
                ts = last if isinstance(last, float) else (last[0] if last else 0)
                if not q or now - ts > max_age:
                    del d[k]


def check_message(rules: list[dict[str, Any]], msg: MessageInfo, *, tracker: RateTracker | None = None,
                  guild_id: int = 0, user_id: int = 0, role_ids: set[int] | None = None,
                  channel_id: int = 0) -> tuple[dict[str, Any], Match] | None:
    """Devuelve la primera regla (por prioridad) que se incumple, o None."""
    role_ids = role_ids or set()
    for rule in sorted(rules, key=lambda r: -int(r.get("priority", 0))):
        if not rule.get("enabled", True):
            continue
        exempt_roles = {int(x) for x in rule.get("exempt_role_ids", [])}
        exempt_channels = {int(x) for x in rule.get("exempt_channel_ids", [])}
        if role_ids & exempt_roles or channel_id in exempt_channels:
            continue
        rt = rule["rule_type"]
        if rt in ("spam", "duplicates"):
            m = tracker.check(rt, rule["config"], guild_id, user_id, msg.content) if tracker else None
        else:
            m = check_static(rt, rule["config"], msg)
        if m:
            return rule, m
    return None
