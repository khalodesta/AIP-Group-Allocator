import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

GENDER_ALIASES={"m":"Male","man":"Male","male":"Male","f":"Female","woman":"Female","female":"Female"}
OFFERING_ALIASES={
    "ai data":"AI & Data","data ai":"AI & Data","ai and data":"AI & Data","data and ai":"AI & Data",
    "customer":"Customer","et p":"ET&P","etp":"ET&P","engineering":"Engineering","cyber":"Cyber"
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

def resolve_university(value: object):
    key=normalize_text(value)
    return university_alias_index().get(key) if key else None

def normalize_university(value: object) -> Optional[str]:
    key=normalize_text(value)
    if not key: return None
    university=resolve_university(value)
    return university["id"] if university else "custom:"+key

def display_university(value: object) -> Optional[str]:
    if value is None or not str(value).strip(): return None
    university=resolve_university(value)
    return university["official_english_name"] if university else str(value).strip()

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
