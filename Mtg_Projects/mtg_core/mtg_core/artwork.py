"""Shared artwork selection metadata, independent of printer and UI modules."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class HighResOverride:
    art_source: str | None = None
    identifier: str | None = None
    name: str | None = None
    dpi: int | None = None
    extension: str | None = None
    download_link: str | None = None
    source_id: int | None = None
    source_name: str | None = None
    small_thumbnail_url: str | None = None
    medium_thumbnail_url: str | None = None
    back_identifier: str | None = None
    back_download_link: str | None = None
    set_code: str | None = None
    collector_number: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "HighResOverride":
        data = deepcopy(dict(data or {}))
        dpi = data.pop("dpi", None)
        source_id = data.pop("source_id", None)
        return cls(
            art_source=_optional_str(data.pop("art_source", None)),
            identifier=_optional_str(data.pop("identifier", None)),
            name=_optional_str(data.pop("name", None)),
            dpi=_optional_int(dpi),
            extension=_optional_str(data.pop("extension", None)),
            download_link=_optional_str(data.pop("download_link", None)),
            source_id=_optional_int(source_id),
            source_name=_optional_str(data.pop("source_name", None)),
            small_thumbnail_url=_optional_str(data.pop("small_thumbnail_url", None)),
            medium_thumbnail_url=_optional_str(data.pop("medium_thumbnail_url", None)),
            back_identifier=_optional_str(data.pop("back_identifier", None)),
            back_download_link=_optional_str(data.pop("back_download_link", None)),
            set_code=_optional_str(data.pop("set_code", None)),
            collector_number=_optional_str(data.pop("collector_number", None)),
            extras=data,
        )

    def to_dict(self) -> dict[str, Any]:
        result = deepcopy(self.extras)
        fields = {
            "art_source": self.art_source,
            "identifier": self.identifier,
            "name": self.name,
            "dpi": self.dpi,
            "extension": self.extension,
            "download_link": self.download_link,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "small_thumbnail_url": self.small_thumbnail_url,
            "medium_thumbnail_url": self.medium_thumbnail_url,
            "back_identifier": self.back_identifier,
            "back_download_link": self.back_download_link,
            "set_code": self.set_code,
            "collector_number": self.collector_number,
        }
        for key, value in fields.items():
            if value is not None:
                result[key] = value
        return result

    def __bool__(self) -> bool:
        return bool(self.to_dict())
