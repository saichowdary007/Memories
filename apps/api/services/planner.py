from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

import pendulum


@dataclass
class QueryPlan:
    intent: str
    filters: Dict[str, str]
    entities: List[str]
    time_range: Dict[str, str] | None


class QueryPlanner:
    TEMPORAL_KEYWORDS = {"when", "schedule", "date", "time", "timeline", "timeline"}

    def classify_intent(self, query: str) -> str:
        if any(word in query.lower() for word in ["when", "schedule", "calendar", "date"]):
            return "temporal"
        if "who" in query.lower() or "person" in query.lower():
            return "entity"
        if any(word in query.lower() for word in ["compare", "analysis", "why", "how"]):
            return "analytical"
        return "factual"

    def extract_entities(self, query: str) -> List[str]:
        pattern = r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*"
        return re.findall(pattern, query)

    def extract_time_range(self, query: str) -> Dict[str, str] | None:
        date_matches = re.findall(r"(\d{4}-\d{2}-\d{2})", query)
        if date_matches:
            start = pendulum.parse(date_matches[0]).to_iso8601_string()
            end = pendulum.parse(date_matches[-1]).to_iso8601_string()
            return {"start": start, "end": end}
        if any(keyword in query.lower() for keyword in self.TEMPORAL_KEYWORDS):
            now = pendulum.now()
            return {"start": now.subtract(months=1).to_iso8601_string(), "end": now.to_iso8601_string()}
        return None

    def plan(self, query: str) -> QueryPlan:
        intent = self.classify_intent(query)
        entities = self.extract_entities(query)
        time_range = self.extract_time_range(query)
        filters: Dict[str, str] = {}
        if time_range:
            filters["time_range"] = f"{time_range['start']}|{time_range['end']}"
        return QueryPlan(intent=intent, filters=filters, entities=entities, time_range=time_range)
