"""Ex5 — reference solution for integrity.py.

verify_dataflow's job: for every concrete fact in the flyer, confirm
that some tool call in the session actually produced that value. If
a fact exists in the flyer but not in any tool output, it's fabrication.

Two competing failure modes to balance:
  - Too lenient → misses fabrications (grader plants £9999; must catch it)
  - Too strict → rejects legitimate flyers (fails the "accepts real flyer" test)

This implementation leans slightly strict but uses the scalar-matching
`fact_appears_in_log` helper provided in the starter to tolerate common
variations (leading £, trailing C, case differences).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: dict
    output: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


_TOOL_CALL_LOG: list[ToolCallRecord] = []


def record_tool_call(tool_name: str, arguments: dict, output: dict) -> None:
    _TOOL_CALL_LOG.append(
        ToolCallRecord(tool_name=tool_name, arguments=dict(arguments), output=dict(output))
    )


def clear_log() -> None:
    _TOOL_CALL_LOG.clear()


@dataclass
class IntegrityResult:
    ok: bool
    unverified_facts: list[str] = field(default_factory=list)
    verified_facts: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "unverified_facts": self.unverified_facts,
            "verified_facts": self.verified_facts,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_money_facts(text: str) -> list[str]:
    """Find all £<number> occurrences, HTML tags stripped or not."""
    # Strip HTML tags first so e.g. <dd>£540</dd> matches cleanly.
    stripped = re.sub(r"<[^>]+>", " ", text)
    return re.findall(r"£\d+(?:\.\d+)?", stripped)


def extract_temperature_facts(text: str) -> list[str]:
    """Find temperature mentions (number followed by °C or C)."""
    stripped = re.sub(r"<[^>]+>", " ", text)
    return list({m.group(1) for m in re.finditer(r"(\d+)\s*°?\s*[Cc]\b", stripped)})


def extract_condition_facts(text: str) -> list[str]:
    """Find weather condition keywords."""
    stripped = re.sub(r"<[^>]+>", " ", text)
    tl = stripped.lower()
    known = ("sunny", "rainy", "cloudy", "partly_cloudy", "partly cloudy")
    return [c for c in known if c in tl]


def extract_testid_facts(text: str) -> dict[str, str]:
    """For HTML flyers that use data-testid, extract {testid: value} pairs.

    This is the preferred path for HTML — it gives us structured facts
    (e.g. {'total': '£540', 'deposit': '£0'}) instead of loose regex
    matches. The solution flyer ships with data-testid on every fact.
    """
    pattern = re.compile(
        r'<[^>]+data-testid="([^"]+)"[^>]*>([^<]+)</[^>]+>',
        re.IGNORECASE,
    )
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(text)}


_HEADING_WORDS = {
    "booking",
    "cost",
    "deposit",
    "event",
    "flyer",
    "party",
    "private",
    "total",
    "venue",
    "weather",
    "forecast",
    "condition",
    "temperature",
    "date",
    "time",
}


def extract_name_facts(text: str) -> list[str]:
    """Extract multi-word capitalized phrases (candidate venue names).

    Filters out phrases that are purely heading words like "Booking Flyer"
    or "Event Weather" to avoid false unverified hits on document chrome.
    """
    stripped = re.sub(r"<[^>]+>", " ", text)
    matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-zA-Z']+){1,4})\b", stripped)
    result: list[str] = []
    for m in matches:
        words = [w.lower() for w in m.split()]
        if all(w in _HEADING_WORDS for w in words):
            continue
        result.append(m)
    return result


def extract_temperature_phrase_facts(text: str) -> list[str]:
    """Extract phrases like 'scorching 35C' (word + number + C).

    Deliberately requires a leading alphabetic word adjacent to the digit
    so legitimate flyer text like 'Temperature: 12C' (which has a colon
    between the heading word and the digit) is not matched and therefore
    not held to this stricter check.
    """
    stripped = re.sub(r"<[^>]+>", " ", text)
    return re.findall(r"\b([a-zA-Z]+\s+\d+\s*°?\s*[Cc])\b", stripped)


def phrase_appears_in_log(phrase: str, log: list[ToolCallRecord] | None = None) -> bool:
    """Looser match than fact_appears_in_log — for multi-word phrases.

    A phrase is accepted if:
      * a log string value is a substring of it (the phrase may add words
        like "Booking — " around a real venue name), or
      * the phrase is a substring of a log string value (the phrase quotes
        a real value), or
      * a log numeric value word-boundary-matches inside the phrase (e.g.
        temperature 12 appearing inside "Temperature 12C").
    """
    records = log if log is not None else _TOOL_CALL_LOG
    target = phrase.lower().strip()

    def _scan(obj: Any) -> bool:
        if isinstance(obj, str):
            o = obj.lower().strip()
            if not o:
                return False
            return target in o or o in target
        if isinstance(obj, bool):
            return False
        if isinstance(obj, (int, float)):
            return bool(re.search(rf"(?<!\d){re.escape(str(obj))}(?!\d)", target))
        if isinstance(obj, dict):
            return any(_scan(v) for v in obj.values())
        if isinstance(obj, (list, tuple, set)):
            return any(_scan(v) for v in obj)
        return False

    return any(_scan(r.output) or _scan(r.arguments) for r in records)


def fact_appears_in_log(fact: Any, log: list[ToolCallRecord] | None = None) -> bool:
    records = log if log is not None else _TOOL_CALL_LOG
    target = str(fact).lower().strip("£°c ")

    def _scan(obj: Any) -> bool:
        if isinstance(obj, (str, int, float)):
            return str(obj).lower().strip("£°c ") == target
        if isinstance(obj, dict):
            return any(_scan(v) for v in obj.values())
        if isinstance(obj, (list, tuple, set)):
            return any(_scan(v) for v in obj)
        return False

    return any(_scan(r.output) or _scan(r.arguments) for r in records)


# ---------------------------------------------------------------------------
# verify_dataflow — the main check
# ---------------------------------------------------------------------------
def verify_dataflow(flyer_content: str) -> IntegrityResult:
    if not flyer_content or not flyer_content.strip():
        return IntegrityResult(ok=True, summary="no facts to verify (empty flyer)")

    scalar_facts: list[str] = []
    scalar_facts.extend(extract_money_facts(flyer_content))
    scalar_facts.extend(extract_temperature_facts(flyer_content))
    scalar_facts.extend(extract_condition_facts(flyer_content))

    phrase_facts: list[str] = []
    phrase_facts.extend(extract_name_facts(flyer_content))
    phrase_facts.extend(extract_temperature_phrase_facts(flyer_content))

    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for f in items:
            key = f.lower().strip()
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out

    scalar_facts = _dedupe(scalar_facts)
    phrase_facts = _dedupe(phrase_facts)

    if not scalar_facts and not phrase_facts:
        return IntegrityResult(
            ok=True, summary="no extractable facts in flyer (verified vacuously)"
        )

    verified: list[str] = []
    unverified: list[str] = []
    for fact in scalar_facts:
        if fact_appears_in_log(fact):
            verified.append(fact)
        else:
            unverified.append(fact)
    for fact in phrase_facts:
        if phrase_appears_in_log(fact):
            verified.append(fact)
        else:
            unverified.append(fact)

    if unverified:
        return IntegrityResult(
            ok=False,
            unverified_facts=unverified,
            verified_facts=verified,
            summary=(
                f"dataflow FAIL: {len(unverified)} unverified fact(s): "
                f"{unverified[:5]}" + ("..." if len(unverified) > 5 else "")
            ),
        )

    return IntegrityResult(
        ok=True,
        verified_facts=verified,
        summary=f"dataflow OK: verified {len(verified)} fact(s) against tool outputs",
    )


__all__ = [
    "IntegrityResult",
    "ToolCallRecord",
    "_TOOL_CALL_LOG",
    "clear_log",
    "extract_condition_facts",
    "extract_money_facts",
    "extract_name_facts",
    "extract_temperature_facts",
    "extract_temperature_phrase_facts",
    "extract_testid_facts",
    "fact_appears_in_log",
    "phrase_appears_in_log",
    "record_tool_call",
    "verify_dataflow",
]
