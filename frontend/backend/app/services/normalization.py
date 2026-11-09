import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

GENDER_ALIASES={"m":"Male","man":"Male","male":"Male","f":"Female","woman":"Female","female":"Female"}
OFFERING_ALIASES={
    "ai data":"AI & Data","data ai":"AI & Data","ai and data":"AI & Data","data and ai":"AI & Data",
    "customer":"Customer","et p":"ET&P","etp":"ET&P","engineering":"Engineering","cyber":"Cyber"
}

UNIVERSITY_CATEGORIES = {"public", "private", "national", "international", "other"}
CATEGORY_GROUPS = {
    "public": "public", "public_technological": "public",
    "private": "private", "private_technological": "private",
    "national_ahlia": "national", "national": "national",
    "foreign_branch": "international", "international_agreement": "international",
    "framework_agreement": "international", "international": "international",
    "special_nature": "other", "government_supervision": "other", "other": "other",
}

def normalize_text(value: object) -> Optional[str]:
    if value is None or not str(value).strip(): return None
    text=str(value).casefold().strip()
    text=re.sub(r"[أإآٱ]","ا",text); text=re.sub(r"ى","ي",text); text=re.sub(r"ة","ه",text); text=re.sub(r"ؤ","و",text); text=re.sub(r"ئ","ي",text)
    text=re.sub(r"[ًٌٍَُِّْـ]","",text)
    return re.sub(r"\s+"," ",re.sub(r"[^\w\s]"," ",text)).strip()

@lru_cache(maxsize=1)
def university_directory():
    path=Path(__file__).resolve().parents[2]/"data"/"university_directory.json"
    if not path.is_file() and getattr(sys, "_MEIPASS", None):
        # The existing PyInstaller spec includes the source backend/data tree.
        path=Path(sys._MEIPASS)/"backend"/"data"/"university_directory.json"
    return json.loads(path.read_text(encoding="utf-8"))["universities"]

@lru_cache(maxsize=1)
def university_alias_index():
    index={}
    for university in university_directory():
        values=[university["official_english_name"],university.get("official_arabic_name"),*university.get("abbreviations",[]),*university.get("english_variations",[]),*university.get("arabic_variations",[])]
        for value in values:
            key=normalize_text(value)
            if key and key not in index: index[key]=university
    return index

def _custom_entry(value: object, custom_universities=None):
    key = normalize_text(value)
    for entry in custom_universities or []:
        item = entry.model_dump() if hasattr(entry, "model_dump") else entry
        if key and any(key == normalize_text(alias) for alias in [item["id"], item["name"], *item.get("aliases", [])]):
            return {**item, "official_english_name": item["name"], "diversity_category": item["category"]}
    return None


def resolve_university(value: object, custom_universities=None):
    custom = _custom_entry(value, custom_universities)
    if custom: return custom
    key=normalize_text(value)
    if not key: return None
    found = university_alias_index().get(key)
    found = found or next((u for u in university_directory() if u["id"] == str(value)), None)
    if found:
        # A correction keyed by stable ID covers every official alias, including
        # aliases not repeated in the administrator's reusable directory.
        return _custom_entry(found["id"], custom_universities) or found
    return None

def normalize_university(value: object, custom_universities=None) -> Optional[str]:
    key=normalize_text(value)
    if not key: return None
    university=resolve_university(value, custom_universities)
    return university["id"] if university else "custom:"+key

def display_university(value: object, custom_universities=None) -> Optional[str]:
    if value is None or not str(value).strip(): return None
    university=resolve_university(value, custom_universities)
    return university["official_english_name"] if university else str(value).strip()


def university_category(value: object, custom_universities=None) -> Optional[str]:
    university = resolve_university(value, custom_universities)
    if not university: return None
    return university.get("diversity_category") or CATEGORY_GROUPS.get(university.get("category"))


def participant_university_category(participant, custom_universities=None) -> Optional[str]:
    attrs = participant.attributes if hasattr(participant, "attributes") else participant.get("attributes", {})
    category = university_category(attrs.get("University"), custom_universities)
    if category: return category
    confirmed = attrs.get("University Category")
    return confirmed if confirmed in UNIVERSITY_CATEGORIES else None


def validate_university_classifications(participants, custom_universities=None):
    unresolved = {}
    confirmed = {}
    for person in participants:
        value = person.attributes.get("University") or "Missing university"
        category = participant_university_category(person, custom_universities)
        if not category:
            unresolved.setdefault(normalize_text(value), str(value))
        else:
            identity = normalize_university(value, custom_universities)
            if identity in confirmed and confirmed[identity] != category:
                raise ValueError(f"University classification required: conflicting categories for {value}. Confirm one category for this university.")
            confirmed[identity] = category
    if unresolved:
        raise ValueError("University classification required: " + ", ".join(unresolved.values()) + ". Confirm a category for each unique university before generating allocations.")

def normalize_gender(value: object) -> Optional[str]:
    normalized=normalize_text(value)
    return normalize_text(GENDER_ALIASES.get(normalized,"")) if normalized else None

def display_gender(value: object) -> Optional[str]:
    normalized=normalize_text(value)
    return GENDER_ALIASES.get(normalized) if normalized else None

def normalize_offering(value: object) -> Optional[str]:
    normalized=normalize_text(value)
    return OFFERING_ALIASES.get(normalized) if normalized else None

def display_offering(value: object) -> Optional[str]:
    if value is None or not str(value).strip(): return None
    return normalize_offering(value) or str(value).strip()
