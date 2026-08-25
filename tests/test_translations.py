"""Regression tests over the shipped translation and custom_sentences files.

With 30 languages of hand-authored JSON/YAML, a typo or a missed key on one
language is easy to miss in review. These tests catch structural drift —
not translation quality, which stays a human/native-speaker concern.
"""
import json
import pathlib

import pytest
import yaml

from custom_components.parcel_aggregator.assist import ASSIST_BUCKETS, describe_bucket

REPO_ROOT = pathlib.Path(__file__).parent.parent
TRANSLATIONS_DIR = REPO_ROOT / "custom_components" / "parcel_aggregator" / "translations"
SENTENCES_DIR = REPO_ROOT / "examples" / "custom_sentences"


def _flatten(data: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update(_flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def _assist_keys(path: pathlib.Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(_flatten(data.get("assist", {})).keys())


@pytest.fixture(scope="module")
def english_assist_keys() -> set[str]:
    return _assist_keys(TRANSLATIONS_DIR / "en.json")


@pytest.mark.parametrize(
    "path", sorted(TRANSLATIONS_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_translation_file_is_valid_json(path):
    json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "path",
    sorted(p for p in TRANSLATIONS_DIR.glob("*.json") if p.stem != "en"),
    ids=lambda p: p.stem,
)
def test_translation_assist_keys_match_english(path, english_assist_keys):
    keys = _assist_keys(path)
    assert keys == english_assist_keys, (
        f"{path.name}: missing {english_assist_keys - keys}, "
        f"extra {keys - english_assist_keys}"
    )


@pytest.mark.parametrize(
    "lang_dir", sorted(d for d in SENTENCES_DIR.iterdir() if d.is_dir()), ids=lambda d: d.name
)
def test_custom_sentences_file_is_valid_and_covers_all_buckets(lang_dir):
    path = lang_dir / "parcel_aggregator.yaml"
    assert path.exists(), f"{lang_dir.name}/parcel_aggregator.yaml is missing"

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["language"] == lang_dir.name

    entries = data["intents"]["ParcelAggregatorGetDetails"]["data"]
    buckets = {entry["slots"]["bucket"] for entry in entries}
    assert buckets == set(ASSIST_BUCKETS)

    for entry in entries:
        assert entry["sentences"], f"{lang_dir.name}: a bucket has no trigger sentences"


# ---------------------------------------------------------------------------
# describe_bucket smoke test — key-parity above only checks key *names*; a
# template with a mismatched {placeholder} inside its value (e.g. {days}
# instead of {day}) would still pass that check and only blow up here, at
# str.format() time.
# ---------------------------------------------------------------------------

_ALL_LANGUAGES = sorted(p.stem for p in TRANSLATIONS_DIR.glob("*.json"))

_PARCEL_WITH_WINDOW = {
    "carrier": "PostNL",
    "sender": "Bol.com",
    "status": "out_for_delivery",
    "planned_from": "2026-06-12T14:00:00Z",
    "planned_to": "2026-06-12T16:00:00Z",
}
_PARCEL_ONLY_START = {
    "carrier": "DHL",
    "sender": "Zalando",
    "status": "in_transit",
    "planned_from": "2026-06-13T09:00:00Z",
    "planned_to": None,
}
_PARCEL_STATUS_ONLY = {
    "carrier": "GLS",
    "sender": None,
    "status": "registered",
    "planned_from": None,
    "planned_to": None,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", _ALL_LANGUAGES)
@pytest.mark.parametrize("bucket", ASSIST_BUCKETS)
async def test_describe_bucket_renders_without_error_empty(hass, language, bucket):
    text = await describe_bucket(hass, {"parcels": []}, bucket, language=language)
    assert text


@pytest.mark.asyncio
@pytest.mark.parametrize("language", _ALL_LANGUAGES)
async def test_describe_bucket_renders_without_error_with_parcels(hass, language):
    info = {
        "parcels": [_PARCEL_WITH_WINDOW, _PARCEL_ONLY_START, _PARCEL_STATUS_ONLY]
    }
    text = await describe_bucket(hass, info, "incoming", language=language)
    assert text
