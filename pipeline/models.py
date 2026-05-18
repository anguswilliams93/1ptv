from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

Status = Literal["unknown", "alive", "dead", "quarantined"]

_QUALITY_SUFFIX_RE = re.compile(r"\b(4K|UHD|FHD|HD|SD)\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


@dataclass
class Channel:
    id: str
    name: str
    url: str
    logo: str | None
    country: str
    categories: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    resolution_height: int | None = None
    group: str | None = None
    status: Status = "unknown"
    last_checked: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Channel":
        return cls(**data)

    def normalized_name(self) -> str:
        without_suffix = _QUALITY_SUFFIX_RE.sub("", self.name)
        return _WS_RE.sub(" ", without_suffix).strip().lower()
