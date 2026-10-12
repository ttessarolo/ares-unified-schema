#!/usr/bin/env python3
"""Build self-contained DACH Loader contract examples from local UMAS schemas.

The UMAS source schemas are inputs only. Generated ingress contracts are
deliberately permissive about presence and unknown fields for technical
forwarding; they are not full-source or business validation contracts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "vela-media-asset-service" / "localstack" / "schemas"
SOURCE_NAMES = ("Movie", "Episode", "Season", "Series", "Clip")
TENANTS = ("JOYN", "JOYN_AT", "JOYN_CH")
SEGMENTS = ("AVOD", "SVOD")
WINDOWS = ("1d", "2d", "7d")
METRICS = ("unique_viewers", "views")
MAX_SAFE_INTEGER = 9007199254740991


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def locate_source_dir(source: Path) -> Path:
    source = source.expanduser().resolve()
    if all((source / f"{name}.schema.json").is_file() for name in SOURCE_NAMES):
        return source
    nested = source / "localstack" / "schemas"
    if all((nested / f"{name}.schema.json").is_file() for name in SOURCE_NAMES):
        return nested
    missing = [name for name in SOURCE_NAMES if not (source / f"{name}.schema.json").is_file()]
    raise FileNotFoundError(
        "--umas-source must be the directory containing the five current "
        "*.schema.json files (or its repository root); missing: " + ", ".join(missing)
    )


def permissive_source_shape(value: Any, property_name: str | None = None) -> Any:
    """Keep source type/value constraints while relaxing structural presence."""
    if isinstance(value, list):
        return [permissive_source_shape(item) for item in value]
    if not isinstance(value, dict):
        return value

    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"required", "minItems", "minProperties", "$id", "$schema"}:
            continue
        if key == "additionalProperties":
            # Existing known nested properties retain their definitions, while
            # forward-compatible payload keys pass through unchanged.
            result[key] = True
            continue
        if property_name == "distributionTenant" and key == "enum":
            # This is an upstream technical input. DACH market selection is a
            # later projection rule, not an ingress rejection rule.
            continue
        if key == "properties" and isinstance(item, dict):
            result[key] = {
                child_name: permissive_source_shape(child, child_name)
                for child_name, child in item.items()
            }
        else:
            result[key] = permissive_source_shape(item)
    if value.get("type") == "object" or "properties" in value:
        result.setdefault("additionalProperties", True)
    return result


def load_content_input(source_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    variants: list[dict[str, Any]] = []
    source_roster: list[dict[str, Any]] = []
    for name in SOURCE_NAMES:
        path = source_dir / f"{name}.schema.json"
        source = json.loads(path.read_text())
        props = source.get("properties")
        if not isinstance(props, dict) or "id" not in props:
            raise ValueError(f"{path}: expected an object schema with root id")
        variant = permissive_source_shape(source)
        variant["type"] = "object"
        variant["properties"]["id"] = {
            "type": "string",
            "pattern": r"^(?!\s*$).+",
            "description": "Required nonblank content identifier.",
        }
        variant["required"] = ["id"]
        variant["additionalProperties"] = True
        variants.append(variant)
        source_roster.append({
            "record": name,
            "source": f"localstack/schemas/{name}.schema.json",
            "sha256": sha256(path),
            "root_property_count": len(props),
            "root_properties": list(props),
        })

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "DACH UMAS Content Loader technical input",
        "description": (
            "Self-contained technical ingress union derived from the five current "
            "UMAS record schemas. Only id is required; all known source properties "
            "are optional here, nested presence/minimum collection sizes are relaxed, "
            "and unknown properties are forwarded. This does not validate complete "
            "source events, full-source update semantics, or DACH business rules. "
            "The DACH projection selects JOYN, JOYN_AT and JOYN_CH downstream."
        ),
        "anyOf": variants,
    }
    return schema, source_roster


def counter_field_names() -> list[str]:
    return [
        f"{metric}_{tenant}_{segment}_{window}"
        for metric in METRICS
        for tenant in TENANTS
        for segment in SEGMENTS
        for window in WINDOWS
    ]


def build_counters_input() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "id": {
            "type": "string",
            "pattern": r"^(?!\s*$).+",
            "description": "Existing content identifier to update.",
        }
    }
    for field in counter_field_names():
        properties[field] = {
            "anyOf": [
                {"type": "integer", "minimum": 0, "maximum": MAX_SAFE_INTEGER},
                {"type": "null"},
            ],
            "description": (
                "Absolute counter snapshot value; null explicitly clears an "
                "unknown or inapplicable value, and zero is a distinct count."
            ),
        }
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "DACH Counters Loader technical input",
        "description": (
            "Complete flat UPDATE snapshot for an existing content id. All 36 "
            "candidate fields are required. Values are absolute assignments, "
            "never increments. Field names, business-model grouping and windows "
            "remain producer proposals."
        ),
        "type": "object",
        "properties": properties,
        "required": ["id", *counter_field_names()],
        "additionalProperties": False,
    }


def keyword() -> dict[str, Any]:
    return {"type": "keyword"}


def text_keyword() -> dict[str, Any]:
    return {"type": "text", "fields": {"keyword": {"type": "keyword"}}}


def date_field() -> dict[str, Any]:
    return {
        "type": "date",
        "format": "strict_date_optional_time",
        "ignore_malformed": False,
    }


def long_field() -> dict[str, Any]:
    return {"type": "long", "coerce": False}


def build_mapping() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "id": keyword(),
        "type": keyword(),
        "entityType": keyword(),
        "publishingStatus": keyword(),
        "productionCountries": keyword(),
        "productionYear": keyword(),
        "number": long_field(),
        "duration": long_field(),
        "cast_name": text_keyword(),
        "crew_name": text_keyword(),
        "cast_role": keyword(),
        "crew_role": keyword(),
        "titles_text": text_keyword(),
        "genres_names_text": text_keyword(),
        "keywords_names_text": text_keyword(),
        "cts_tags_value": text_keyword(),
        "age_ratings_min_age": long_field(),
        "age_ratings_type": keyword(),
        "relevant_airing_info_datetime": date_field(),
        "relevant_airing_info_distribution_tenant": keyword(),
        "broadcast_date_joyn": date_field(),
        "broadcast_date_joyn_at": date_field(),
        "broadcast_date_joyn_ch": date_field(),
        "active_distribution_tenants": keyword(),
        "active_distribution_models": keyword(),
        "active_access_rules": keyword(),
        "active_brand_codes": keyword(),
        # Reserved proposal only: Brand Search ownership/source remains open.
        "brand_names": text_keyword(),
        # Text is deliberately analyzer-neutral until the fingerprint contract is set.
        "fingerprint_super": {"type": "text"},
        "fingerprint_metadata": {"type": "text"},
        "fingerprint": {"type": "text"},
        "lastARESLoaderModified": date_field(),
    }
    for field in counter_field_names():
        properties[field] = long_field()

    return {
        "mappings": {
            "dynamic": "strict",
            "_meta": {
                "status": "configuration proposal; review required before deployment",
                "scope": "DACH JOYN, JOYN_AT, JOYN_CH",
                "notes": [
                    "No shards, analyzers, aliases, or deployment settings are specified.",
                    "broadcastDate source aliases are intentionally omitted; the three per-tenant derived fields are authoritative.",
                    "visibilities is intentionally omitted from indexed output.",
                    "brand_names is reserved pending Product/API confirmation.",
                    "Fingerprint formats/analyzers remain open.",
                    "lastARESLoaderModified is assigned from the ISO UTC Ingress envelope timestamp (ares-ingress/lib/transformPayload.ts) and passed through by Content Loader (ares-content-loader/lib/service.ts).",
                    "duration is integer in all three UMAS source records that declare it, with source maximum 9007199254740991; OpenSearch long avoids 32-bit truncation.",
                    "productionYear remains keyword because all five UMAS schemas declare string-or-null.",
                    "number and age_ratings_min_age preserve source integer range using OpenSearch long.",
                ],
            },
            "properties": properties,
        }
    }


def nullable_string() -> dict[str, Any]:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def nullable_date_time() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "string", "format": "date-time"},
            {"type": "null"},
        ]
    }


def string_array(nullable: bool = True) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "string"}
    if nullable:
        item = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {"anyOf": [{"type": "array", "items": item}, {"type": "null"}]}


def int_array(nullable: bool = True) -> dict[str, Any]:
    item = {"type": "integer"}
    if nullable:
        item = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    return {"anyOf": [{"type": "array", "items": item}, {"type": "null"}]}


def build_content_output_contract() -> dict[str, Any]:
    """Support schema for the flattened Content Loader output projection."""
    properties: dict[str, Any] = {
        "id": {
            "type": "string",
            "pattern": r"^(?!\s*$).+",
            "description": "Content identity; retained by flat output.",
        },
        "type": nullable_string(),
        "entityType": nullable_string(),
        "publishingStatus": nullable_string(),
        "productionCountries": string_array(nullable=False),
        "productionYear": nullable_string(),
        "number": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "duration": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
        "cast_name": string_array(),
        "crew_name": string_array(),
        "titles_text": string_array(),
        "genres_names_text": string_array(),
        "keywords_names_text": string_array(),
        "cast_role": string_array(),
        "crew_role": string_array(),
        "cts_tags_value": string_array(),
        "age_ratings_min_age": int_array(),
        "age_ratings_type": string_array(),
        "relevant_airing_info_datetime": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "anyOf": [
                            {"type": "string", "format": "date-time"},
                            {"type": "null"},
                        ]
                    },
                },
                {"type": "null"},
            ]
        },
        "relevant_airing_info_distribution_tenant": string_array(),
        "broadcast_date_joyn": nullable_date_time(),
        "broadcast_date_joyn_at": nullable_date_time(),
        "broadcast_date_joyn_ch": nullable_date_time(),
        "active_distribution_tenants": {"type": "array", "items": {"type": "string"}},
        "active_distribution_models": {"type": "array", "items": {"type": "string"}},
        "active_access_rules": {"type": "array", "items": {"type": "string"}},
        "active_brand_codes": {"type": "array", "items": {"type": "string"}},
        "fingerprint_super": {
            "type": "string",
            "description": "UMAS-side contribution used by the candidate Merge configuration.",
        },
        "brand_names": string_array(),
    }
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "DACH UMAS flat Content Loader output support contract",
        "description": (
            "Support schema for schema.output after flat-v1 projection. It is not a "
            "third ingress schema. Optional source roots such as entityType and number "
            "remain optional because not all five record kinds declare them. The four "
            "active arrays and three derived tenant dates are required so the normalizer "
            "can emit explicit empty/null resets. Independent relevant-airing arrays do "
            "not prove tenant/date tuple correlation. Fingerprint target/contribution "
            "fields and Counters Loader fields are excluded."
        ),
        "type": "object",
        "properties": properties,
        "required": [
            "id",
            "broadcast_date_joyn",
            "broadcast_date_joyn_at",
            "broadcast_date_joyn_ch",
            "active_distribution_tenants",
            "active_distribution_models",
            "active_access_rules",
            "active_brand_codes",
            "fingerprint_super",
        ],
        "additionalProperties": False,
    }


def make_synthetic_content() -> dict[str, Any]:
    return {
        "id": "synthetic-dach-content-001",
        "type": "MOVIE",
        "entityType": "MOVIE",
        "source": "synthetic-fixture",
        "publishingStatus": "ACTIVE",
        "titles": [
            {
                "text": "Synthetischer DACH-Titel",
                "type": "main",
                "language": {"code": "deu", "standard": "ISO-639-2"},
            }
        ],
        "productionCountries": ["DE"],
        "productionYear": "2026",
        "duration": 90,
        "relevantAiringInfo": [
            {
                "distributionTenant": "JOYN",
                "datetime": "2026-10-12T10:00:00Z",
                "streamId": "synthetic-stream-1",
            },
            {"distributionTenant": "MEDIASET_IT"},
        ],
        "visibilities": [
            {
                "type": "AVOD",
                "distributionTenant": "JOYN",
                "requiredAccessRights": ["synthetic-free"],
                "brandCodes": ["synthetic-brand-code"],
                "timeslots": [],
            },
            {
                "type": "SVOD",
                "distributionTenant": "JOYN_AT",
                "requiredAccessRights": [],
                "brandCodes": [],
                "timeslots": [],
            },
            {
                "type": "AVOD",
                "distributionTenant": "JOYN_CH",
                "requiredAccessRights": [],
                "brandCodes": [],
                "timeslots": [],
            },
        ],
    }


def make_synthetic_counters() -> dict[str, Any]:
    result: dict[str, Any] = {"id": "synthetic-dach-content-001"}
    for field in counter_field_names():
        result[field] = None
    result["unique_viewers_JOYN_AVOD_1d"] = 12
    result["views_JOYN_AVOD_1d"] = 42
    return result


def build_profiles() -> dict[str, Any]:
    selected = [
        "id", "type", "entityType", "publishingStatus", "titles[].text",
        "genres[].names[].text", "keywords[].names[].text", "cast[].name",
        "cast[].role", "crew[].name", "crew[].role", "productionCountries",
        "productionYear", "duration", "number", "ctsTags[].value",
        "ageRatings[].minAge", "ageRatings[].type", "relevantAiringInfo[].datetime",
        "relevantAiringInfo[].distributionTenant", "visibilities[].distributionTenant",
        "visibilities[].type", "visibilities[].requiredAccessRights", "visibilities[].brandCodes",
        "visibilities[].timeslots[].start", "visibilities[].timeslots[].end",
    ]
    return {
        "status": "reviewable configuration description; not directly deployable",
        "scope": {"tenants": list(TENANTS)},
        "profiles": {
            "umas_content": {
                "role": "full-source UMAS ingestion and flat projection",
                "input_schema": "outputs/schemas/content-loader.schema.json",
                "output_contract_support": "outputs/contracts/content-output-contract.json",
                "idField": "id", "index": "<shared content write index>",
                "candidate_token_actions": ["uw", "d"],
                "deactivation_action": "uw with full source and publishingStatus=INACTIVE",
                "full_source_requirement": "All non-delete events contain the full source document. Only d is ID-only; the input schema cannot enforce action-specific completeness.",
                "flatJsonOutput": True,
                "merge": {
                    "enabled": True, "merge": ["fingerprint_super"],
                    "with": ["fingerprint_metadata"], "to": "fingerprint",
                    "missing_stored_contribution": "empty string",
                    "incoming_target": "must not be supplied",
                },
                "pipeline": {
                    "active": True, "projection_stage": "first inside ares-pipeline",
                    "egress_injection_required": True,
                    "fingerprint_destination": "fingerprint_super",
                    "fingerprint_rules": "keys, boosts and token format pending configuration",
                },
                "selected_source_paths": selected,
                "conditional_derived_include": ["brand_names only when Brand enrichment is enabled"],
                "input_decorator_only_source_paths": ["ageRatings[].ratingSystem"],
                "filter_predicate_paths": ["titles[].language.code", "titles[].type", "genres[].names[].language.code", "keywords[].names[].language.code"],
                "filters": [
                    "titles[language.code=deu][type=main]",
                    "genres[].names[language.code=deu]",
                    "keywords[].names[language.code=deu]",
                    "visibilities[distributionTenant=JOYN|JOYN_AT|JOYN_CH]",
                    "relevantAiringInfo[distributionTenant=JOYN|JOYN_AT|JOYN_CH]",
                ],
                "scheduling": {
                    "index": "<dedicated schedule index>",
                    "schedules": [{
                        "keys": {"root": "visibilities[].timeslots", "start": "start", "end": "end"},
                        "applyCurrentState": True, "skipPastEvents": True,
                        "excludeFromOutput": True, "destroyExpired": False,
                        "events": {
                            "start": {"active": True, "evaluator": "state-based aggregate evaluator to configure"},
                            "end": {"active": True, "evaluator": "same state-based evaluator"},
                            "destroy": {"active": False},
                        },
                        "context": ["distributionTenant", "type", "requiredAccessRights", "brandCodes"],
                        "membership": "start <= current time < end",
                    }],
                },
                "output_decorator_contract": {
                    "date_source": "relevantAiringInfo[].datetime from the same distributionTenant entry",
                    "static_date_map": {"JOYN": "broadcast_date_joyn", "JOYN_AT": "broadcast_date_joyn_at", "JOYN_CH": "broadcast_date_joyn_ch"},
                    "date_reset": "Emit every configured date field on each full-source update; null for absent tenant or datetime.",
                    "airing_cardinality": "zero or one entry per tenant; duplicate/invalid values are errors, never max(datetime)",
                    "missing_owned_visibility_root": "normalise to [] before scheduling under the full-source contract",
                    "other_owned_resets": "emit [] for absent selected lists and null for absent selected nullable scalars; never reset Metadata/counter fields",
                    "relevant_airing_output": "retain selected flattened arrays; derived tenant fields are authoritative for date queries",
                },
                "state_aggregate_outputs": ["active_distribution_tenants", "active_distribution_models", "active_access_rules", "active_brand_codes"],
                "state_evaluator": "Rebuild every aggregate from eligible $active windows; return [true,payload]. INACTIVE or no eligible windows emits all four arrays as [].",
                "open_items": ["Tuple encoding and escaping", "Invalid-window error handling", "Brand Product/API confirmation", "Fingerprint rules and analysis", "Rating exceptions and JOYN_CH applicability"],
            },
            "metadata": {
                "role": "parallel enrichment; detailed fields/provider out of scope",
                "candidate_token_actions": ["u"], "idField": "id", "index": "<shared content write index>",
                "create_on_missing_content": False,
                "merge": {"enabled": True, "merge": ["fingerprint_metadata"], "with": ["fingerprint_super"], "to": "fingerprint"},
                "field_ownership": "Own metadata plus own fingerprint contribution only; extend strict mapping before activation.",
                "notifications": "AWS external configuration; producer decides next action; no automatic resubmission",
            },
            "counters": {
                "role": "dedicated counter snapshot UPDATE on existing content",
                "input_schema": "outputs/schemas/counters-loader.schema.json",
                "output_schema": "outputs/schemas/counters-loader.schema.json",
                "idField": "id", "index": "<shared content write index>",
                "candidate_token_actions": ["u"], "create_on_missing_content": False,
                "flatJsonOutput": False, "pipeline": {"active": False},
                "merge": {"active": False}, "schedules": [], "decorators": [],
                "counter_semantics": "Absolute assignment of complete owned snapshot; null clears unknown/inapplicable, zero is measured. No increments or fingerprint writes.",
                "initial_cadence": "once daily from Analytics; independent of continuous UMAS lane",
                "open_items": ["Producer confirmation of 36 fields, AVOD/SVOD labels, paired views windows and null convention", "Deployed missing-content failure path"],
            },
        },
    }


def build_roster(source_roster: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "candidate roster; field semantics and deployment configuration require review",
        "source_schemas": source_roster,
        "content_input": {
            "schema": "outputs/schemas/content-loader.schema.json",
            "records": list(SOURCE_NAMES),
            "required_root_fields": ["id"],
            "unknown_fields": "accepted and forwarded",
            "nested_required_and_minimum_collection_constraints": "removed for technical ingress",
            "market_projection_filter": ["JOYN", "JOYN_AT", "JOYN_CH"],
            "business_validation": "not provided by this schema",
        },
        "counters": {
            "schema": "outputs/schemas/counters-loader.schema.json",
            "id_required": True,
            "field_count": len(counter_field_names()),
            "field_pattern": "{unique_viewers|views}_{JOYN|JOYN_AT|JOYN_CH}_{AVOD|SVOD}_{1d|2d|7d}",
            "fields": counter_field_names(),
            "value": f"integer 0..{MAX_SAFE_INTEGER} or null; all fields required in a complete snapshot",
            "status": "Names, AVOD/SVOD-to-free/plus mapping, paired windows for views and null absence convention are producer proposals; DACH viewer windows 1d/2d/7d are agreed.",
        },
        "mapping": {
            "file": "outputs/opensearch/dach-content.mapping.json",
            "field_count": len(build_mapping()["mappings"]["properties"]),
            "status": "strict mapping proposal; not deployment-ready",
            "open": [
                "fingerprint representation and analyzers",
                "Brand names source and Product requirement",
            ],
        },
        "support_contract": {
            "file": "outputs/contracts/content-output-contract.json",
            "purpose": "Content Loader flat schema.output support; not a third ingress schema",
            "required_fields": build_content_output_contract()["required"],
            "shared_fingerprint_target_metadata_contribution_and_counters_excluded": True,
            "normalizer_emission_required_before_validation": [
                "three derived tenant dates as null on reset",
                "four active arrays as [] on reset",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--umas-source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Directory containing Movie/Episode/Season/Series/Clip schema JSON, or repository root.",
    )
    args = parser.parse_args()
    source_dir = locate_source_dir(args.umas_source)

    content_input, source_roster = load_content_input(source_dir)
    counters_input = build_counters_input()
    mapping = build_mapping()
    content_output = build_content_output_contract()
    profiles = build_profiles()
    synthetic_content = make_synthetic_content()
    synthetic_counters = make_synthetic_counters()
    roster = build_roster(source_roster)

    outputs = {
        ROOT / "outputs/schemas/content-loader.schema.json": content_input,
        ROOT / "outputs/schemas/counters-loader.schema.json": counters_input,
        ROOT / "outputs/opensearch/dach-content.mapping.json": mapping,
        ROOT / "outputs/contracts/loader-profiles.json": profiles,
        ROOT / "outputs/contracts/synthetic-content.json": synthetic_content,
        ROOT / "outputs/contracts/synthetic-counters.json": synthetic_counters,
        ROOT / "outputs/contracts/content-output-contract.json": content_output,
        ROOT / "outputs/contracts/contract-roster.json": roster,
    }
    for path, value in outputs.items():
        write_json(path, value)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
