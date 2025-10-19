"""
fuzzy.py
--------
Lightweight fuzzy date/time parsing helpers for scheduling.
Converts phrases like "later next week", "tomorrow morning", "next Friday afternoon"
into concrete timezone-aware [start, end) ranges you can query against Availability.

Usage:
    from scheduling.fuzzy import parse_fuzzy_date_range
    start, end = parse_fuzzy_date_range("later next week")
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, time, timezone
from typing import Optional, Tuple

from django.utils import timezone as dj_tz  # assume Django timezone is present

from google import genai 
from google.genai import types
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

client = genai.Client()

@dataclass
class FuzzyContext:
    """Minimal context used by the LLM: business hours and a clock source."""
    open_time: time = time(hour=9, minute=0)
    close_time: time = time(hour=17, minute=0)

    def get_now(self) -> datetime:
        return dj_tz.now()


def _llm_parse_range(text: str, now: datetime, ctx: FuzzyContext) -> Tuple[datetime, datetime]:
    """Ask the LLM to return a JSON object {start, end} as ISO datetimes. Exceptions propagate."""
    system_prompt = (
        "You are a strict ISO8601 datetime parser. "
        "Given a human time phrase and the current time, return a JSON object with exactly two keys: "
        "'start' and 'end', both full ISO-8601 datetimes including timezone offset. "
        "Return ONLY the JSON object and nothing else."
    )
    user_prompt = (
        f"Now: 2025, {now.isoformat()}\n"
        f"Business open: {ctx.open_time.isoformat()}, close: {ctx.close_time.isoformat()}\n"
        f"Phrase: {text}\n\n"
        "Interpret the phrase as the next reasonable time window within business hours. Timeslots are 30 minutes long"
        "If the phrase implies a single day use the business open/close bounds. Use the same timezone as 'Now'."
        "Example questions and answers:\n"
        "Q: 'tomorrow morning' → A: {\"start\": \"2024-06-12T09:00:00+00:00\", \"end\": \"2024-06-12T12:00:00+00:00\"}\n"
        "Q: 'next friday' → A: {\"start\": \"2025-06-14T09:00:00+00:00\", \"end\": \"2025-06-14T17:00:00+00:00\"}\n"
        "Q: 'next week' → A: {\"start\": \"2022-11-20T09:00:00+00:00\", \"end\": \"2022-11-24T17:00:00+00:00\"}\n"
    )

    completion = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=json.dumps([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]),
    )
    
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", completion.text.strip())
    parsed = json.loads(cleaned)

    return datetime.fromisoformat(parsed["start"]), datetime.fromisoformat(parsed["end"])

def parse_fuzzy_date_range(text: str, ctx: Optional[FuzzyContext] = None) -> Tuple[datetime, datetime]:
    """
    Parse a human time phrase into a concrete [start, end) datetime range using the LLM.
    If the LLM call raises, the exception will propagate to the caller.
    """
    ctx = ctx or FuzzyContext()
    now = ctx.get_now()
    return _llm_parse_range(text, now, ctx)


def human_range(start: datetime, end: datetime) -> str:
    fmt = "%a %Y-%m-%d %H:%M"
    return f"[{start.strftime(fmt)} → {end.strftime(fmt)})"

