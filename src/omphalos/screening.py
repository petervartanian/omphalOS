"""Explainable list-record candidates; no automatic identity or legal decisions."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from .sources import effective_date_issues
from .util import canonical_json, sha256_bytes

# Keep large candidate sets from exhausting a browser workspace.
# Crossing this limit yields unavailable coverage, never a truncated clean result.
MAX_RETAINED_CANDIDATES = 10_000

# These identify organizational form, not a particular legal entity. Only full
# phrases are removed for descriptive wording: "research" or "production" alone
# may be part of a distinctive name. Original names and aliases are never edited.
_ORGANIZATION_PHRASES = (
    "federal state unitary enterprise",
    "public joint stock company",
    "open joint stock company",
    "closed joint stock company",
    "joint stock company",
    "limited liability company",
    "public limited company",
    "private limited company",
    "research and production association",
    "scientific and production association",
    "research production association",
    "scientific production association",
    "research and production enterprise",
    "scientific and production enterprise",
    "research production enterprise",
    "scientific production enterprise",
    "научно производственное объединение",
    "научно производственное предприятие",
    "публичное акционерное общество",
    "открытое акционерное общество",
    "закрытое акционерное общество",
    "акционерное общество",
    "общество с ограниченнои ответственностью",
    "nauchno proizvodstvennoe obedinenie",
    "nauchno proizvodstvennoye obyedineniye",
)
_ORGANIZATION_WORDING = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _ORGANIZATION_PHRASES) + r")\b"
)
_ORGANIZATION_FORMS = frozenset(
    {
        "company",
        "corporation",
        "incorporated",
        "limited",
        "ltd",
        "llc",
        "llp",
        "plc",
        "corp",
        "inc",
        "co",
        "jsc",
        "pjsc",
        "ojsc",
        "cjsc",
        "npo",
        "gmbh",
        "нпо",
        "ооо",
        "оао",
        "зао",
        "пао",
        "ао",
    }
)


# ALA-LC Russian (2012), modern alphabet only. This is a supplementary
# *candidate* path, not Unicode normalization or identity equivalence. Its
# normalized search form drops diacritics and hard/soft signs. Historical and
# other Cyrillic alphabets deliberately need an explicit supplied alias.
_RUSSIAN_ROMANIZATION = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        (
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "ë",
            "zh",
            "z",
            "i",
            "ĭ",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "kh",
            "ts",
            "ch",
            "sh",
            "shch",
            "",
            "y",
            "",
            "ė",
            "iu",
            "ia",
        ),
        strict=True,
    )
)
_ROMANIZATION_METHOD = "russian_ala_lc_2012_normalized"


def _romanized_russian(value: str) -> str | None:
    # NFC preserves ё and й; compatibility decomposition before mapping would
    # silently replace them with е and и. Reject mixed-script words/names and
    # unsupported letters instead of treating visual confusables as equivalents.
    text = unicodedata.normalize("NFC", value).casefold()
    letters = [char for char in text if char.isalpha()]
    if not letters or any(char not in _RUSSIAN_ROMANIZATION for char in letters):
        return None
    if any(unicodedata.category(char).startswith("M") for char in text):
        return None
    return "".join(_RUSSIAN_ROMANIZATION.get(char, char) for char in text)


def normalized_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(
        "".join(
            c if c.isalnum() else " "
            for c in decomposed
            if not unicodedata.combining(c)
        ).split()
    )


@dataclass(frozen=True)
class _PreparedName:
    original: str
    normalized: str
    ordered: str
    counts: dict[str, int]


def _prepare_name(value: str) -> _PreparedName:
    normalized = normalized_name(value)
    return _PreparedName(
        value,
        normalized,
        " ".join(sorted(normalized.split())),
        dict(Counter(normalized)),
    )


def _score_prepared(a: _PreparedName, b: _PreparedName) -> Decimal:
    if not a.normalized or not b.normalized:
        return Decimal(0)
    if a.normalized == b.normalized or a.ordered == b.ordered:
        return Decimal(1)

    def score(x: str, y: str) -> Decimal:
        matching = sum(
            block.size
            for block in SequenceMatcher(
                None, x, y, autojunk=False
            ).get_matching_blocks()
        )
        return Decimal(2 * matching) / Decimal(len(x) + len(y))

    ordinary = score(a.normalized, b.normalized)
    if a.normalized == a.ordered and b.normalized == b.ordered:
        return ordinary
    return max(ordinary, score(a.ordered, b.ordered))


def name_score(left: str, right: str) -> Decimal:
    """Maximum exact character/token-order similarity, not a probability."""
    return _score_prepared(_prepare_name(left), _prepare_name(right))


def _can_reach(
    a: _PreparedName, b: _PreparedName, numerator: int, denominator: int
) -> bool:
    """Character intersection is an upper bound for both exact matching variants.

    This only prunes impossible candidates. It uses integer comparisons, so it
    cannot remove a candidate due to rounding near the requested threshold.
    """
    total = len(a.normalized) + len(b.normalized)
    if (
        not total
        or 2 * min(len(a.normalized), len(b.normalized)) * denominator
        < numerator * total
    ):
        return False
    common = sum(min(count, b.counts.get(char, 0)) for char, count in a.counts.items())
    return 2 * common * denominator >= numerator * total


@dataclass(frozen=True)
class _CandidateName:
    full: _PreparedName
    distinctive: _PreparedName
    primary: bool
    romanized: _PreparedName | None
    romanized_distinctive: str
    latin: bool


def _distinctive_name(normalized: str) -> str:
    return " ".join(
        token
        for token in _ORGANIZATION_WORDING.sub(" ", normalized).split()
        if token not in _ORGANIZATION_FORMS
    )


def _prepare_candidate_name(value: str, *, primary: bool = False) -> _CandidateName:
    full = _prepare_name(value)
    distinct = _distinctive_name(full.normalized)
    romanization = _romanized_russian(value)
    romanized = _prepare_name(romanization) if romanization is not None else None
    return _CandidateName(
        full,
        _prepare_name(distinct),
        primary,
        romanized,
        normalized_name(_romanized_russian(distinct) or "") if romanized else "",
        bool(full.normalized)
        and all(
            char in "abcdefghijklmnopqrstuvwxyz0123456789 " for char in full.normalized
        ),
    )


def _organization_comparison(
    a: _CandidateName, b: _CandidateName, known: bool, infer: bool
) -> bool:
    # Unknown source categories also receive the guard when both names contain
    # organizational wording. Personal-name comparisons otherwise stay unchanged.
    if (
        a.full.normalized == b.full.normalized or a.full.ordered == b.full.ordered
    ) and (
        a.distinctive.normalized
        or b.distinctive.normalized
        or (a.primary and b.primary)
    ):
        # Exact name/token matches remain candidates even if phrase stripping is
        # asymmetric. A wholly generic alias does not establish a name match.
        return False
    return known or (
        infer
        and a.full.normalized != a.distinctive.normalized
        and b.full.normalized != b.distinctive.normalized
    )


def _candidate_name_score(
    a: _CandidateName, b: _CandidateName, organization: bool
) -> tuple:
    raw = _score_prepared(a.full, b.full)
    distinctive = _score_prepared(a.distinctive, b.distinctive) if organization else raw
    adjusted = (
        Decimal(0)
        if organization
        and (not a.distinctive.normalized or not b.distinctive.normalized)
        else min(raw, (raw + distinctive) / Decimal(2))
    )
    return (
        adjusted,
        a.full.original,
        b.full.original,
        raw,
        a.distinctive.normalized if organization else a.full.normalized,
        b.distinctive.normalized if organization else b.full.normalized,
        distinctive,
        organization,
        "normalized",
        a.full.normalized,
        b.full.normalized,
    )


def _romanized_comparison(a: _CandidateName, b: _CandidateName) -> tuple | None:
    if a.romanized and b.latin:
        left, right = a.romanized, b.full
        left_core, right_core = a.romanized_distinctive, b.distinctive.normalized
    elif a.latin and b.romanized:
        left, right = a.full, b.romanized
        left_core, right_core = a.distinctive.normalized, b.romanized_distinctive
    else:
        return None
    # No fuzzy expansion of a lossy transformation. Require the complete token
    # multiset, including organizational forms, and at least three distinctive
    # letters on each side. Single-letter lookalikes and generic forms alone do
    # not create new candidates. Explicit supplied aliases still compare normally.
    if left.ordered != right.ordered or any(
        sum(char.isalpha() for char in core) < 3 for core in (left_core, right_core)
    ):
        return None
    raw = _score_prepared(a.full, b.full)
    return (
        Decimal(1),
        a.full.original,
        b.full.original,
        raw,
        a.full.normalized,
        b.full.normalized,
        raw,
        False,
        _ROMANIZATION_METHOD,
        left.normalized,
        right.normalized,
    )


def _comparison_rank(comparison: tuple) -> tuple:
    # Supplied exact names/aliases take precedence over a derived search form.
    return comparison[0], comparison[8] == "normalized", comparison


def _identifier(value: str) -> str:
    return "".join(c for c in value.upper() if c.isalnum())


_IDENTIFIER_FIELDS = {
    "lei": "lei",
    "legal entity identifier": "lei",
    "legal entity identifier lei": "lei",
    "legal entity number": "lei",
    "registration": "registration_id",
    "registration id": "registration_id",
    "registration number": "registration_id",
    "company number": "registration_id",
    "company registration number": "registration_id",
    "business registration number": "registration_id",
    "commercial registry number": "registration_id",
}


def _identifier_field(kind: str) -> str | None:
    # Type labels identify a namespace. OFAC uses Company Number and Legal
    # Entity Number as well as Registration Number and LEI. Never infer a
    # corporate registration from substrings in Alien/Tax/Vehicle Registration.
    return _IDENTIFIER_FIELDS.get(normalized_name(kind))


def _entity_category(value: str | None) -> str | None:
    value = normalized_name(value or "")
    if value in {
        "entity",
        "organization",
        "organisation",
        "company",
        "corporation",
        "business",
    }:
        return "organization"
    if value in {"person", "individual"}:
        return "individual"
    return value if value in {"vessel", "aircraft"} else None


def eligible_screening_entities(entities: list[dict]) -> list[dict]:
    """Require a name/alias or supported identifier that survives normalization."""
    return [
        entity
        for entity in entities
        if any(
            normalized_name(name)
            for name in [entity["name"], *entity.get("aliases", [])]
        )
        or any(
            _identifier(entity.get(field) or "") for field in ("lei", "registration_id")
        )
    ]


def applicable_source_records(
    snapshot: dict, as_of: date
) -> tuple[list[dict], set[str]]:
    """Retain unknown/contradictory intervals; exclude only consistent dated bounds."""
    entries = snapshot["entries"]
    inconsistent_dates = {
        issue["record_id"] for issue in effective_date_issues(entries)
    }
    return [
        entry
        for entry in entries
        if entry.get("record_id") in inconsistent_dates
        or not (
            (entry.get("start_date") and entry["start_date"] > as_of.isoformat())
            or (entry.get("end_date") and entry["end_date"] < as_of.isoformat())
        )
    ], inconsistent_dates


def candidate_findings(
    entities: list[dict],
    snapshot: dict,
    as_of: date,
    *,
    minimum_score: Decimal = Decimal("0.90"),
    max_candidates: int = 5,
) -> tuple[list[dict], dict]:
    # Retained for archived case compatibility. A presentation preference must
    # never suppress qualifying source records from analytical output.
    del max_candidates
    entries = snapshot["entries"]
    considered, inconsistent_dates = applicable_source_records(snapshot, as_of)
    eligible_entities = eligible_screening_entities(entities)
    findings = []
    retained_exact_or_identifier = 0
    retained_approximate = 0
    retained_transliterated = 0
    total_retained = 0
    entities_compared = 0
    # Prepare Unicode, sorted tokens, and character counts only once per source name.
    prepared = [
        (
            entry,
            [
                _prepare_candidate_name(name, primary=index == 0)
                for index, name in enumerate([entry["name"], *entry.get("aliases", [])])
            ],
        )
        for entry in considered
    ]
    threshold_numerator, threshold_denominator = minimum_score.as_integer_ratio()
    # If full similarity cannot exceed one, the mean cannot reach the requested
    # threshold unless distinctive similarity can reach 2 * threshold - 1.
    core_numerator, core_denominator = max(
        Decimal(0), 2 * minimum_score - 1
    ).as_integer_ratio()
    for entity in eligible_entities:
        entities_compared += 1
        candidates = []
        names = [
            _prepare_candidate_name(name, primary=index == 0)
            for index, name in enumerate([entity["name"], *entity.get("aliases", [])])
        ]
        for entry, source_names in prepared:
            categories = (
                _entity_category(entity.get("entity_type")),
                _entity_category(entry.get("entity_type")),
            )
            non_organization = any(
                category in {"individual", "vessel", "aircraft"}
                for category in categories
            )
            known_organization = "organization" in categories and not non_organization
            infer_organization = all(category is None for category in categories)
            best = (
                Decimal(0),
                "",
                "",
                Decimal(0),
                "",
                "",
                Decimal(0),
                False,
                "normalized",
                "",
                "",
            )
            for name in names:
                for source_name in source_names:
                    romanized = _romanized_comparison(name, source_name)
                    if romanized is not None and _comparison_rank(
                        romanized
                    ) > _comparison_rank(best):
                        best = romanized
                    if not _can_reach(
                        name.full,
                        source_name.full,
                        threshold_numerator,
                        threshold_denominator,
                    ):
                        continue
                    organization = _organization_comparison(
                        name, source_name, known_organization, infer_organization
                    )
                    if organization and not _can_reach(
                        name.distinctive,
                        source_name.distinctive,
                        core_numerator,
                        core_denominator,
                    ):
                        continue
                    score = _candidate_name_score(name, source_name, organization)
                    if _comparison_rank(score) > _comparison_rank(best):
                        best = score
            matched_ids = []
            identifier_comparisons = []
            for ident in entry.get("identifiers", []):
                if not isinstance(ident, dict):
                    continue
                number = ident.get("idNumber") or ident.get("number")
                kind = str(ident.get("idType") or ident.get("type") or "")
                if not isinstance(number, str):
                    continue
                field = _identifier_field(kind)
                if field and entity.get(field):
                    source_identifier = _identifier(number)
                    entity_identifier = _identifier(entity[field])
                    if not source_identifier or not entity_identifier:
                        continue
                    same = source_identifier == entity_identifier
                    identifier_comparisons.append(
                        {
                            "field": field,
                            "source_type": kind,
                            "entity_value": entity[field],
                            "source_value": number,
                            "comparison": "equal" if same else "different",
                        }
                    )
                    if same:
                        matched_ids.append(
                            {"field": field, "source_type": kind, "value": number}
                        )
            if best[0] < minimum_score and not matched_ids:
                continue
            if matched_ids and best[0] < minimum_score:
                # For identifier-only candidates, report the actual best name score,
                # not the zero sentinel used while pruning non-candidates.
                best = max(
                    _candidate_name_score(
                        name,
                        source_name,
                        _organization_comparison(
                            name, source_name, known_organization, infer_organization
                        ),
                    )
                    for name in names
                    for source_name in source_names
                )
            countries = entry.get("countries", [])
            country_context = "unknown"
            # Only compare like-for-like ISO codes; OFAC country labels are not ISO codes.
            iso_countries = [c for c in countries if re.fullmatch(r"[A-Z]{2}", c)]
            if entity.get("country") and iso_countries:
                country_context = (
                    "corroborates" if entity["country"] in iso_countries else "differs"
                )
            candidates.append(
                (
                    best[0],
                    entry["record_id"],
                    entry,
                    best,
                    matched_ids,
                    country_context,
                    identifier_comparisons,
                )
            )
        candidates.sort(key=lambda item: (not bool(item[4]), -item[0], item[1]))
        # Every qualifying source record is retained. Sorting is presentation,
        # never a top-N analytical cutoff; source records can represent different
        # lists or programs even when their names and scores are identical.
        retained = candidates
        retained_exact_or_identifier += sum(
            bool(candidate[4])
            or (candidate[0] == 1 and candidate[3][8] == "normalized")
            for candidate in retained
        )
        retained_transliterated += sum(
            not candidate[4] and candidate[3][8] == _ROMANIZATION_METHOD
            for candidate in retained
        )
        retained_approximate += sum(
            not candidate[4] and candidate[0] < 1 for candidate in retained
        )
        total_retained += len(retained)
        if total_retained > MAX_RETAINED_CANDIDATES:
            # Check before building findings for this entity. Drop earlier
            # findings too: a partial screening must not resemble a completed
            # result. The lower bound is explicit because later entities have
            # not been compared.
            return [], {
                "entities_considered": entities_compared,
                "entities_without_usable_identity": len(entities)
                - len(eligible_entities),
                "source_records_considered": len(considered),
                "source_records_excluded_by_dates": len(entries) - len(considered),
                "source_records_with_inconsistent_dates": len(inconsistent_dates),
                "candidates_omitted_by_display_limit": 0,
                "candidates_retained_exact_or_identifier": 0,
                "candidates_retained_approximate": 0,
                "candidates_retained_transliterated": 0,
                "candidate_output_limit_exceeded": True,
                "candidate_output_limit": MAX_RETAINED_CANDIDATES,
                "candidate_count_at_least": total_retained,
            }
        for _, _, entry, best, ids, country_context, id_comparisons in retained:
            key = [entity["entity_id"], snapshot["snapshot_id"], entry["record_id"]]
            alias_quality = [
                a.get("quality")
                for a in entry.get("alias_details", [])
                if a.get("name") == best[2]
            ]
            left_type, right_type = _entity_category(
                entity.get("entity_type")
            ), _entity_category(entry.get("entity_type"))
            type_context = (
                "unknown"
                if not left_type or not right_type
                else "corroborates" if left_type == right_type else "differs"
            )
            findings.append(
                {
                    "finding_id": "screening_candidates-"
                    + sha256_bytes(canonical_json(key))[:24],
                    "investigation_id": "screening_candidates",
                    "title": "Official-list identity candidate",
                    "observation": f"Entity {entity['entity_id']} has a name or identifier candidate in {entry['list_name']}: {entry['name']}. This requires identity review.",
                    "entity_ids": [entity["entity_id"]],
                    "record_refs": [
                        {"table": "entities", "record_id": entity["entity_id"]}
                    ],
                    "metrics": {
                        "candidate_selection": (
                            "typed_identifier"
                            if ids
                            else (
                                "transliterated_name"
                                if best[8] == _ROMANIZATION_METHOD
                                else (
                                    "exact_normalized_name"
                                    if best[0] == 1
                                    else "approximate_name"
                                )
                            )
                        ),
                        "candidates_for_entity": len(candidates),
                        "approximate_candidates_omitted_for_entity": 0,
                        "name_similarity": format(
                            best[0].quantize(Decimal("0.0001")), "f"
                        ),
                        "minimum_similarity": str(minimum_score),
                        "entity_name_compared": best[1],
                        "source_name_compared": best[2],
                        "full_name_similarity": format(
                            best[3].quantize(Decimal("0.0001")), "f"
                        ),
                        **(
                            {
                                "entity_distinctive_name": best[4],
                                "source_distinctive_name": best[5],
                                "distinctive_name_similarity": format(
                                    best[6].quantize(Decimal("0.0001")), "f"
                                ),
                            }
                            if best[7]
                            else {}
                        ),
                        "name_transformation": best[8],
                        "entity_comparison_form": best[9],
                        "source_comparison_form": best[10],
                        "name_comparison_method": (
                            "Exact full-token comparison after modern Russian ALA-LC (2012) romanization and search normalization; diacritics and hard/soft signs are omitted. This lossy search form is a candidate aid, not identity equivalence. Original-script full-name similarity is reported separately."
                            if best[8] == _ROMANIZATION_METHOD
                            else (
                                "Organization similarity is the lower of full-name similarity and the mean of full-name and distinctive-name similarities. Shared organizational wording is downweighted."
                                if best[7]
                                else "Full normalized name comparison."
                            )
                        ),
                        "identifier_matches": ids,
                        "identifier_comparisons": id_comparisons,
                        "entity_type_context": type_context,
                        "entity_type_supplied": entity.get("entity_type"),
                        "source_entity_type": entry.get("entity_type"),
                        "country_context": country_context,
                        "source_countries": entry.get("countries", []),
                        "alias_quality": alias_quality,
                        "listing_start_date": entry.get("start_date"),
                        "listing_end_date": entry.get("end_date"),
                        **(
                            {"listing_date_status": "inconsistent_source_interval"}
                            if entry["record_id"] in inconsistent_dates
                            else {}
                        ),
                        "source_updated_at": snapshot.get("metadata", {}).get(
                            "source_updated_at"
                        ),
                        "list_name": entry["list_name"],
                        "programs": entry.get("programs", []),
                    },
                    "unknowns": [
                        "Identity equivalence and the legal effect of this specific listing require independent review.",
                        "Missing listing dates do not establish membership on the case's historical as-of date.",
                    ]
                    + (
                        [
                            "The candidate uses a lossy Russian romanization search form. Language, spelling variants, and identity must be checked against original-script records and authoritative identifiers."
                        ]
                        if best[8] == _ROMANIZATION_METHOD
                        else []
                    )
                    + (
                        [
                            "The source end date precedes its start date. Listing applicability on the case's as-of date cannot be evaluated; both supplied dates are retained without correction."
                        ]
                        if entry["record_id"] in inconsistent_dates
                        else []
                    ),
                    "alternatives": [
                        "Unrelated people or organizations may share a name, alias, or an unqualified registration number."
                    ],
                    "falsifiers": [
                        "Authoritative identity documents, dates of birth, full addresses, or registration jurisdictions may establish that these are different entities."
                    ],
                    "source_refs": [
                        {
                            "snapshot_id": snapshot["snapshot_id"],
                            "record_id": entry["record_id"],
                            "source_id": snapshot["source_id"],
                        }
                    ],
                }
            )
    return findings, {
        "entities_considered": len(eligible_entities),
        "entities_without_usable_identity": len(entities) - len(eligible_entities),
        "source_records_considered": len(considered),
        "source_records_excluded_by_dates": len(entries) - len(considered),
        "source_records_with_inconsistent_dates": len(inconsistent_dates),
        "candidates_omitted_by_display_limit": 0,
        "candidates_retained_exact_or_identifier": retained_exact_or_identifier,
        "candidates_retained_approximate": retained_approximate,
        "candidates_retained_transliterated": retained_transliterated,
        "candidate_output_limit_exceeded": False,
        "candidate_output_limit": MAX_RETAINED_CANDIDATES,
        "candidate_count_at_least": total_retained,
    }
