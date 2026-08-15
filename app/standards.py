from __future__ import annotations

import re
from typing import Any


BRAND_SEEDS: dict[str, list[str]] = {
    "Apple": ["Apple", "苹果", "iTunes", "ITUNE", "itunes", "苹果卡"],
    "Razer": ["Razer", "razer", "雷蛇", "绿蛇", "欧蛇"],
    "Xbox": ["Xbox", "XBOX", "xbox"],
    "Steam": ["Steam", "蒸汽"],
    "Roblox": ["Roblox", "ROBLOX"],
    "PSN": ["PSN", "PlayStation", "psn"],
    "Google Play": ["Google Play", "google play", "谷歌", "GP"],
    "Amazon": ["Amazon", "亚马逊", "美亚", "英亚", "德亚", "加亚", "澳亚", "意亚"],
    "Paysafecard": ["Paysafecard", "paysafecard", "paysafe", "PSC"],
    "Visa": ["Visa", "VISA"],
    "Amex": ["Amex", "AMEX", "American Express", "美国运通"],
    "Sephora": ["Sephora", "SEPHORA"],
    "Footlocker": ["Footlocker", "Foot Locker", "FOOTLOCKER"],
    "Macy": ["Macy", "Macy's", "MACY"],
    "Nike": ["Nike", "NIKE"],
    "Nordstrom": ["Nordstrom", "NORDSTROM"],
    "Vanilla": ["Vanilla", "VANILLA"],
    "Eneba": ["Eneba", "ENEBA"],
    "Transcash": ["Transcash", "TRANSCASH"],
}

DEFAULT_SAME_RATE_BRANDS = {"Razer", "Steam", "Xbox", "Roblox"}

DEFAULT_US_MARKET_BRANDS = {
    "Sephora",
    "Footlocker",
    "Macy",
    "Nike",
    "Nordstrom",
    "Vanilla",
    "Amex",
    "Visa",
    "Eneba",
    "Transcash",
}

RAW_CARD_SUBTYPE_OPTIONS = [
    "卡图",
    "横白",
    "横卡",
    "白卡",
    "竖卡",
    "散卡",
    "整卡",
    "整卡/散卡",
    "代码/卡密",
    "电子卡",
    "普通物理卡",
]

MARKET_DISPLAY_NAMES = {
    "US": "美国",
    "UK": "英国",
    "EU": "欧盟",
    "Netherlands": "荷兰",
    "France": "法国",
    "Germany": "德国",
    "Belgium": "比利时",
    "Ireland": "爱尔兰",
    "Austria": "奥地利",
    "Italy": "意大利",
    "Spain": "西班牙",
    "Portugal": "葡萄牙",
    "Slovakia": "斯洛伐克",
    "Croatia": "克罗地亚",
    "Greece": "希腊",
    "Finland": "芬兰",
    "Slovenia": "斯洛文尼亚",
    "Bulgaria": "保加利亚",
    "Romania": "罗马尼亚",
    "Saudi Arabia": "沙特",
    "Canada": "加拿大",
    "Australia": "澳大利亚",
    "New Zealand": "新西兰",
    "Hong Kong": "香港",
    "Switzerland": "瑞士",
    "Singapore": "新加坡",
    "Malaysia": "马来西亚",
    "Brazil": "巴西",
    "Mexico": "墨西哥",
    "Thailand": "泰国",
    "Philippines": "菲律宾",
    "Japan": "日本",
    "South Africa": "南非",
    "India": "印度",
    "Indonesia": "印度尼西亚",
    "Turkey": "土耳其",
    "Poland": "波兰",
    "Czech Republic": "捷克",
    "Hungary": "匈牙利",
    "Denmark": "丹麦",
    "Sweden": "瑞典",
    "Norway": "挪威",
    "Chile": "智利",
    "Colombia": "哥伦比亚",
    "United Arab Emirates": "阿联酋",
    "Israel": "以色列",
    "Taiwan": "台湾",
    "South Korea": "韩国",
}

MARKET_SEEDS: list[dict[str, Any]] = [
    {"country": "US", "currency": "USD", "aliases": ["US", "USA", "美国", "美区", "美卡", "美亚", "USD"]},
    {"country": "UK", "currency": "GBP", "aliases": ["UK", "英国", "英区", "英亚", "GBP"]},
    {"country": "EU", "currency": "EUR", "aliases": ["EU", "EUR", "欧盟", "欧洲", "欧元"]},
    {"country": "Netherlands", "currency": "EUR", "aliases": ["Netherlands", "荷兰"]},
    {"country": "France", "currency": "EUR", "aliases": ["France", "法国"]},
    {"country": "Germany", "currency": "EUR", "aliases": ["Germany", "德国", "德区", "德亚"]},
    {"country": "Belgium", "currency": "EUR", "aliases": ["Belgium", "比利时"]},
    {"country": "Ireland", "currency": "EUR", "aliases": ["Ireland", "爱尔兰"]},
    {"country": "Austria", "currency": "EUR", "aliases": ["Austria", "奥地利"]},
    {"country": "Italy", "currency": "EUR", "aliases": ["Italy", "意大利", "意区", "意亚"]},
    {"country": "Spain", "currency": "EUR", "aliases": ["Spain", "西班牙"]},
    {"country": "Portugal", "currency": "EUR", "aliases": ["Portugal", "葡萄牙"]},
    {"country": "Slovakia", "currency": "EUR", "aliases": ["Slovakia", "斯洛伐克"]},
    {"country": "Croatia", "currency": "EUR", "aliases": ["Croatia", "克罗地亚"]},
    {"country": "Greece", "currency": "EUR", "aliases": ["Greece", "希腊"]},
    {"country": "Finland", "currency": "EUR", "aliases": ["Finland", "芬兰"]},
    {"country": "Slovenia", "currency": "EUR", "aliases": ["Slovenia", "斯洛文尼亚"]},
    {"country": "Bulgaria", "currency": "BGN", "aliases": ["Bulgaria", "保加利亚", "BGN"]},
    {"country": "Romania", "currency": "RON", "aliases": ["Romania", "罗马尼亚", "RON"]},
    {"country": "Saudi Arabia", "currency": "SAR", "aliases": ["Saudi Arabia", "Saudi", "KSA", "沙特", "沙特阿拉伯", "SAR"]},
    {"country": "Canada", "currency": "CAD", "aliases": ["Canada", "加拿大", "加区", "加亚", "CAD"]},
    {"country": "Australia", "currency": "AUD", "aliases": ["Australia", "澳洲", "澳大利亚", "澳区", "澳元", "澳亚", "AUD"]},
    {"country": "New Zealand", "currency": "NZD", "aliases": ["New Zealand", "新西兰", "纽西兰", "NZD"]},
    {"country": "Hong Kong", "currency": "HKD", "aliases": ["Hong Kong", "HK", "香港", "港区", "HKD"]},
    {"country": "Switzerland", "currency": "CHF", "aliases": ["Switzerland", "Swiss", "瑞士", "CHF"]},
    {"country": "Singapore", "currency": "SGD", "aliases": ["Singapore", "新加坡", "SGD"]},
    {"country": "Malaysia", "currency": "MYR", "aliases": ["Malaysia", "马来西亚", "MYR"]},
    {"country": "Brazil", "currency": "BRL", "aliases": ["Brazil", "巴西", "BRL"]},
    {"country": "Mexico", "currency": "MXN", "aliases": ["Mexico", "墨西哥", "MX", "MXN"]},
    {"country": "Thailand", "currency": "THB", "aliases": ["Thailand", "泰国", "THB"]},
    {"country": "Philippines", "currency": "PHP", "aliases": ["Philippines", "菲律宾", "PHP"]},
    {"country": "Japan", "currency": "JPY", "aliases": ["Japan", "日本", "日区", "JPY"]},
    {"country": "South Africa", "currency": "ZAR", "aliases": ["South Africa", "南非", "ZAR"]},
    {"country": "India", "currency": "INR", "aliases": ["India", "印度", "INR"]},
    {"country": "Indonesia", "currency": "IDR", "aliases": ["Indonesia", "印尼", "印度尼西亚", "IDR"]},
    {"country": "Turkey", "currency": "TRY", "aliases": ["Turkey", "土耳其", "TRY"]},
    {"country": "Poland", "currency": "PLN", "aliases": ["Poland", "波兰", "PLN"]},
    {"country": "Czech Republic", "currency": "CZK", "aliases": ["Czech Republic", "Czech", "捷克", "CZK"]},
    {"country": "Hungary", "currency": "HUF", "aliases": ["Hungary", "匈牙利", "HUF"]},
    {"country": "Denmark", "currency": "DKK", "aliases": ["Denmark", "丹麦", "DKK"]},
    {"country": "Sweden", "currency": "SEK", "aliases": ["Sweden", "瑞典", "SEK"]},
    {"country": "Norway", "currency": "NOK", "aliases": ["Norway", "挪威", "NOK"]},
    {"country": "Chile", "currency": "CLP", "aliases": ["Chile", "智利", "CLP"]},
    {"country": "Colombia", "currency": "COP", "aliases": ["Colombia", "哥伦比亚", "COP"]},
    {"country": "United Arab Emirates", "currency": "AED", "aliases": ["United Arab Emirates", "UAE", "迪拜阿联酋", "阿联酋", "AED"]},
    {"country": "Israel", "currency": "ILS", "aliases": ["Israel", "以色列", "ILS"]},
    {"country": "Taiwan", "currency": "TWD", "aliases": ["Taiwan", "台湾", "台区", "TWD"]},
    {"country": "South Korea", "currency": "KRW", "aliases": ["South Korea", "Korea", "韩国", "韩区", "KR", "KRW"]},
]

NORMALIZED_CARD_SUBTYPE_OPTIONS = [
    "卡图",
    "代码",
    "电子卡",
    "竖卡",
    "待确认",
]

MATCH_SUBTYPE_OPTIONS = NORMALIZED_CARD_SUBTYPE_OPTIONS

APPLE_NORMALIZED_SUBTYPE_OPTIONS = ["卡图", "竖卡", "代码", "电子卡"]
NON_APPLE_NORMALIZED_SUBTYPE_OPTIONS = ["卡图", "代码", "电子卡"]


def normalize_card_subtype(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "待确认"
    lower = raw.lower()
    compact = re.sub(r"[\s_\-/]+", "", lower)

    if any(token in raw for token in ["竖卡", "竖版卡"]) or "vertical" in lower:
        return "竖卡"
    if "电子" in raw or any(
        token in lower for token in ["e-code", "e-card", "ecard", "digital", "email delivery", "email card"]
    ):
        return "电子卡"
    if any(token in raw for token in ["代码", "卡密", "代码/卡密"]) or any(
        token in lower for token in ["code only", "pin"]
    ) or compact == "code":
        return "代码"
    if any(token in raw for token in ["卡图", "横白", "横卡", "白卡", "散卡", "整卡", "普通物理卡", "实体图", "图片", "物理卡", "横版卡"]):
        return "卡图"
    return "待确认"


def normalize_card_subtype_for_brand(
    brand: str | None,
    value: str | None,
    frontend_type: str | None = "",
) -> str:
    normalized = normalize_card_subtype(value)
    if normalized == "待确认":
        if frontend_type == "physical":
            normalized = "卡图"
        elif frontend_type == "code":
            normalized = "代码"
    if (brand or "").strip() != "Apple" and normalized == "竖卡":
        return "卡图"
    return normalized


def normalized_subtype_options_for_brand(brand: str | None) -> list[str]:
    clean_brand = (brand or "").strip()
    if clean_brand == "Apple":
        return list(APPLE_NORMALIZED_SUBTYPE_OPTIONS)
    if clean_brand:
        return list(NON_APPLE_NORMALIZED_SUBTYPE_OPTIONS)
    return list(NORMALIZED_CARD_SUBTYPE_OPTIONS)


def normalize_brand(text: str | None) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    candidates: list[tuple[str, str]] = []
    for brand, aliases in BRAND_SEEDS.items():
        candidates.extend((brand, alias) for alias in aliases)
    for brand, alias in sorted(candidates, key=lambda item: len(item[1]), reverse=True):
        if _alias_in_text(value, alias):
            return brand
    return ""


def normalize_market(country_text: str | None, currency_text: str | None = "") -> tuple[str, str]:
    combined = f"{country_text or ''} {currency_text or ''}".strip()
    if not combined:
        return "", ""

    # Prefer the full Indonesia name over the shorter overlapping alias "印度".
    if any(_market_alias_in_text(combined, alias) for alias in ["印度尼西亚", "印尼", "IDR"]):
        return "Indonesia", "IDR"

    specific = _market_variants(combined, include_generic_eu=False)
    has_eur = has_generic_eur(combined)
    if len(specific) == 1:
        return specific[0]
    if len(specific) > 1:
        return "EU", "EUR"

    for market in MARKET_SEEDS:
        if market["country"] == "EU" and market["currency"] == "EUR":
            if any(_market_alias_in_text(combined, alias) for alias in market["aliases"]):
                return "EU", "EUR"
            break
    if has_eur:
        return "EU", "EUR"
    return "", ""


def eur_country_variants(text: str | None) -> list[tuple[str, str]]:
    return _market_variants(text or "", include_generic_eu=False, currency="EUR")


def has_generic_eur(text: str | None) -> bool:
    value = text or ""
    return any(_market_alias_in_text(value, alias) for alias in ["EU", "EUR", "欧盟", "欧洲", "欧元"])


def market_value(country: str | None, currency: str | None) -> str:
    country_value = (country or "").strip()
    currency_value = (currency or "").strip().upper()
    if not country_value or not currency_value:
        return ""
    return f"{country_value}|{currency_value}"


def market_label(country: str | None, currency: str | None) -> str:
    country_value = (country or "").strip()
    currency_value = (currency or "").strip().upper()
    if not country_value or not currency_value:
        return ""
    display_name = MARKET_DISPLAY_NAMES.get(country_value)
    if display_name:
        return f"{display_name} / {country_value} / {currency_value}"
    return f"{country_value} / {currency_value}"


def is_open_ended_range(
    denom_min: Any,
    denom_max: Any,
    source_text: str | None,
    range_type: str | None = None,
) -> bool:
    if denom_min in (None, "") or denom_max not in (None, ""):
        return False
    normalized_type = (range_type or "").strip().lower()
    if normalized_type:
        return normalized_type == "open"
    minimum = float(denom_min)
    pattern = re.compile(
        r"(?:(?:>=|≥)\s*(?P<leading>\d+(?:\.\d+)?)|(?P<trailing>\d+(?:\.\d+)?)\s*(?:以上|\+))"
    )
    for match in pattern.finditer(source_text or ""):
        value = float(match.group("leading") or match.group("trailing"))
        if abs(value - minimum) < 0.000001:
            return True
    return False


def split_market_value(value: str | None) -> tuple[str, str]:
    raw = (value or "").strip()
    if not raw:
        return "", ""
    if "|" in raw:
        country, currency = raw.split("|", 1)
        return country.strip(), currency.strip().upper()
    if "/" in raw:
        country, currency = raw.split("/", 1)
        return country.strip(), currency.strip().upper()
    return normalize_market(raw)


def standard_market_values() -> set[str]:
    return {market_value(item["country"], item["currency"]) for item in MARKET_SEEDS}


def standard_brand_names() -> set[str]:
    return set(BRAND_SEEDS)


def _market_variants(text: str, include_generic_eu: bool = True, currency: str | None = None) -> list[tuple[str, str]]:
    variants = []
    for market in MARKET_SEEDS:
        if currency and market["currency"] != currency:
            continue
        if not include_generic_eu and market["country"] == "EU":
            continue
        if any(_market_alias_in_text(text, alias) for alias in market["aliases"]):
            variants.append((market["country"], market["currency"]))
    return list(dict.fromkeys(variants))


def _alias_in_text(text: str, alias: str) -> bool:
    if _contains_cjk(alias):
        return alias in text
    normalized_text = text.lower()
    normalized_alias = re.escape(alias.lower())
    normalized_alias = normalized_alias.replace(r"\ ", r"\s*")
    return bool(re.search(rf"(?<![a-z0-9]){normalized_alias}(?![a-z0-9])", normalized_text))


def _market_alias_in_text(text: str, alias: str) -> bool:
    if _contains_cjk(alias):
        return alias in text
    normalized_text = text.lower()
    normalized_alias = re.escape(alias.lower())
    normalized_alias = normalized_alias.replace(r"\ ", r"\s*")
    return bool(re.search(rf"(?<![a-z0-9]){normalized_alias}(?=$|[^a-z0-9])", normalized_text))


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))
