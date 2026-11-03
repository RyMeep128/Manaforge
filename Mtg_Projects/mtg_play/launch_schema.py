"""Private launch boundary schema. Never send this all-decks payload to Unity."""

from mtg_core.decks import DECK_SCHEMA_VERSION
from .contracts import GAME_PROTOCOL_VERSION
from .launch_manifest import LAUNCH_MANIFEST_VERSION, MAX_DECK_ENTRIES


def launch_schema():
    string = {"type": "string"}
    optional = {"anyOf": [string, {"type": "null"}]}

    def record(properties):
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    def reference(name):
        return {"$ref": f"#/$defs/{name}"}

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:manaforge:play:launch-manifest:1",
        "title": "Private one-time native deck projection; not a persistent deck format",
        "$ref": "#/$defs/LaunchManifest",
        "$defs": {
            "NativeLaunchEntry": record(
                {
                    "entry_id": string,
                    "name": string,
                    "quantity": {"type": "integer", "minimum": 1},
                    "section": {"enum": ["mainboard", "sideboard", "commander"]},
                    "card_id": optional,
                    "oracle_id": optional,
                    "set_code": optional,
                    "collector_number": optional,
                    "owned": {"type": "integer", "minimum": 0},
                    "image_asset_id": optional,
                    "backside_asset_id": optional,
                }
            ),
            "NativeLaunchDeck": record(
                {
                    "deck_id": string,
                    "name": string,
                    "format": string,
                    "entries": {
                        "type": "array",
                        "items": reference("NativeLaunchEntry"),
                        "maxItems": MAX_DECK_ENTRIES,
                    },
                    "commander_entry_ids": {"type": "array", "items": string},
                    "companion_entry_id": optional,
                }
            ),
            "NativeLaunchDocument": record(
                {
                    "schema_version": {"const": DECK_SCHEMA_VERSION},
                    "deck": reference("NativeLaunchDeck"),
                }
            ),
            "LaunchSeat": record(
                {
                    "seat_id": string,
                    "name": string,
                    "controller": {"enum": ["local_human", "engine_ai"]},
                    "deck_owner_id": optional,
                    "document": reference("NativeLaunchDocument"),
                }
            ),
            "LaunchEnginePin": record(
                {
                    "engine_version": string,
                    "adapter_version": string,
                    "artifact_manifest_sha256": string,
                }
            ),
            "LaunchManifest": record(
                {
                    "launch_manifest_version": {"const": LAUNCH_MANIFEST_VERSION},
                    "protocol_version": {"const": GAME_PROTOCOL_VERSION},
                    "manifest_id": string,
                    "manaforge_version": string,
                    "engine": reference("LaunchEnginePin"),
                    "format": {"enum": ["freeform", "commander"]},
                    "seats": {
                        "type": "array",
                        "items": reference("LaunchSeat"),
                        "minItems": 2,
                    },
                }
            ),
        },
    }
