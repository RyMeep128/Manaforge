"""Export the existing Python DTO shapes, without creating a new wire protocol."""

from dataclasses import fields, is_dataclass
import types
from typing import Literal, Union, get_args, get_origin, get_type_hints

from . import contracts


def _shape(annotation):
    primitives = {str: "string", int: "integer", bool: "boolean", type(None): "null"}
    if annotation in primitives:
        return {"type": primitives[annotation]}
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (types.UnionType, Union):
        return {"anyOf": [_shape(value) for value in arguments]}
    if origin is Literal:
        return {"enum": list(arguments)}
    if origin is tuple:
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return {"type": "array", "items": _shape(arguments[0])}
        return {
            "type": "array",
            "prefixItems": [_shape(value) for value in arguments],
            "items": False,
            "minItems": len(arguments),
            "maxItems": len(arguments),
        }
    if is_dataclass(annotation):
        return {"$ref": f"#/$defs/{annotation.__name__}"}
    raise TypeError(f"Unsupported contract annotation: {annotation!r}")


def contract_schema():
    definitions = {}
    for name, record in vars(contracts).items():
        if not isinstance(record, type) or not is_dataclass(record):
            continue
        hints = get_type_hints(record)
        properties = {field.name: _shape(hints[field.name]) for field in fields(record)}
        if "protocol_version" in properties:
            properties["protocol_version"] = {"const": contracts.GAME_PROTOCOL_VERSION}
        if "revision" in properties:
            properties["revision"]["minimum"] = 0
        definition = {
            "type": "object",
            "properties": properties,
            # to_dict emits defaults too. Optional Python constructors do not
            # mean fields are absent from the current serialized output.
            "required": list(properties),
            "additionalProperties": False,
        }
        if name == "TargetReference":
            definition["anyOf"] = [
                {
                    "properties": {
                        "object_id": {"type": "string"},
                        "player_id": {"type": "null"},
                    }
                },
                {
                    "properties": {
                        "object_id": {"type": "null"},
                        "player_id": {"type": "string"},
                    }
                },
            ]
            properties["ordinal"] = {
                "anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}]
            }
            properties["amount"] = {
                "anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]
            }
        if name == "TargetingContext":
            properties["selected"]["maxItems"] = 256
            for key in ("minimum", "maximum"):
                properties[key] = {
                    "anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]
                }
        if name == "StackTargets":
            properties["targets"]["maxItems"] = 256
        if name == "GameSnapshot":
            properties["stack_targets"]["anyOf"][0]["maxItems"] = 4096
            definition["required"].remove("decision_error")
            definition["required"].remove("session_notice")
        if name == "ChoiceRequest":
            definition["required"].remove("groups")
            definition["required"].remove("request")
            properties["groups"]["anyOf"][0].update(minItems=2, maxItems=2)
        if name == "ChoiceGroup":
            properties["cards"]["maxItems"] = 256
        if name == "ChoicePreview":
            properties["rules"]["anyOf"][0]["maxItems"] = 128
        private_fields = {
            "ChoicePreview": ("name", "type_line", "rules"),
            "GameObject": (
                "characteristics",
                "card_identity",
                "commander_id",
                "copy_source_id",
                "presentation_id",
            ),
            "CardObservation": (
                "name",
                "set_code",
                "collector_number",
                "group_id",
                "group_label",
                "oracle_id",
                "printing_id",
            ),
        }.get(name)
        if private_fields:
            definition["allOf"] = [
                {
                    "if": {
                        "properties": {"hidden": {"const": True}},
                        "required": ["hidden"],
                    },
                    "then": {
                        "properties": {
                            field: {"type": "null"} for field in private_fields
                        }
                    },
                }
            ]
        definitions[name] = definition
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:manaforge:play:python-contracts:1",
        "title": "Python protocol 1 serialized DTO baseline; not a network envelope",
        "$defs": definitions,
    }
