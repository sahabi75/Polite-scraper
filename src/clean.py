import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ValidationError, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


class Book(BaseModel):
    """The shape of a finished, clean record."""
    title: str
    product_url: str
    price_text: str
    price_gbp: float
    availability_text: str
    rating_text: str
    description: Optional[str] = None  # the only optional field
    source_page: str
    fetched_at: str

    @field_validator("product_url", "source_page")
    @classmethod
    def must_be_https(cls, value):
        if not value.startswith("https://"):
            raise ValueError("URL must start with https://")
        return value

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, value):
        if not value.strip():
            raise ValueError("title is empty")
        return value

    @field_validator("price_gbp")
    @classmethod
    def price_not_negative(cls, value):
        if value < 0:
            raise ValueError("price cannot be negative")
        return value


def parse_price(price_text):
    """'£51.77' -> 51.77. Returns None if no number is found."""
    if not price_text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", price_text)
    if match is None:
        return None
    return float(match.group())


def normalize(raw):
    """Add the clean value next to the raw one. The raw text is kept."""
    clean = dict(raw)
    clean["price_gbp"] = parse_price(raw.get("price_text"))
    return clean


def format_errors(error):
    """Turn a Pydantic error into one readable line."""
    parts = []
    for err in error.errors():
        field = ".".join(str(x) for x in err["loc"])
        parts.append(f"{field}: {err['msg']}")
    return "; ".join(parts)


def save_json(data, filename):
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_and_store(raw_records):
    """Normalize + validate every record. Good ones go to books.json,
    bad ones go to errors.json with a reason."""
    good = {}  # keyed by product_url, so duplicates count once
    errors = []

    for raw in raw_records:
        record = normalize(raw)
        try:
            book = Book(**record)
        except ValidationError as e:
            errors.append({
                "product_url": raw.get("product_url"),
                "reason": format_errors(e),
                "record": raw,
            })
            continue
        good[book.product_url] = book.model_dump()

    save_json(list(good.values()), "books.json")
    save_json(errors, "errors.json")
    return len(good), len(errors)
