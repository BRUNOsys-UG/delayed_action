"""Persistent task model."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


@dataclass(frozen=True)
class Task:
    task_id: str
    entity_id: str
    action: str
    due: datetime
    data: dict[str, Any]

    def serialize(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "entity_id": self.entity_id,
                "action": self.action, "due": self.due.isoformat(), "data": self.data}

    @classmethod
    def deserialize(cls, raw: dict[str, Any]) -> "Task":
        due = dt_util.parse_datetime(raw["due"])
        if due is None or due.tzinfo is None:
            raise ValueError("Invalid stored due time")
        return cls(raw["task_id"], raw["entity_id"], raw["action"],
                   dt_util.as_utc(due), dict(raw["data"]))
