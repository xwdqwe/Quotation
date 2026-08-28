from __future__ import annotations

import re
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Any

from .money import decimal_text
from .standards import (
    DEFAULT_SAME_RATE_BRANDS,
    DEFAULT_US_MARKET_BRANDS,
    NORMALIZED_CARD_SUBTYPE_OPTIONS,
    eur_country_variants,
    has_generic_eur,
    normalize_brand,
    normalize_card_subtype,
    normalize_card_subtype_for_brand,
    normalize_market,
    split_market_value,
)


METHOD_LABELS = {
    "fast_card": "快卡",
    "fast_process": "快刷",
    "slow_process": "慢刷",
}

METHOD_FEEDBACK_NOTES = {
    "quick_fast_process": "极速快刷，约1-5分钟",
    "web_fast_process": "快刷网单，约10-15分钟",
    "fast_process": "快刷，约5-20分钟",
    "fast_card": "快卡，约1-2分钟",
    "slow_process": "慢刷，慢反馈",
}

STATUS_LABELS = {
    "active": "正常",
    "ask_first": "发前问",
    "paused": "暂停",
    "unavailable": "不收",
    "warning": "风险提醒",
    "pending": "待处理",
    "revoked": "已撤回",
    "superseded": "已覆盖",
    "expired": "已过期",
    "need_update": "需处理",
    "update_needed": "建议更新",
    "no_change": "无变化",
    "synced_to_admin": "已同步到管理后台",
    "filled_zero": "已在管理后台填0",
    "ignored": "暂不处理",
    "auto_closed_no_change": "自动关闭-无变化",
    "initial_confirm": "首次确认",
    "first_confirm": "首次确认",
    "suggest_pause": "建议暂停",
    "no_cover_quote": "无承接报价",
    "manual_review": "人工确认",
    "risk_changed": "风险复核",
    "abnormal_review": "异常复核",
}

SUBTYPE_OPTIONS = [
    "横卡",
    "竖卡",
    "白卡",
    "卡图",
    "整卡/散卡",
    "代码/卡密",
    "电子卡",
    "普通物理卡",
    "待确认",
]

COMMENT_PREFIX_RE = re.compile(r"^\s*(?:#|(?:注|提示|注意)\s*[:：])")
SEPARATOR_RE = re.compile(r"^[=\-_\s—–]+$")
PRICE_RE = re.compile(r"(?:(?<![<>])=+|[:：](?![^=]*=))\s*[【\[\(（]?\s*(?P<rate>\d+(?:\.\d+)?)")
BRACKET_RATE_RE = re.compile(r"[【\[]\s*(?P<rate>\d+(?:\.\d+)?)\s*[】\]]")
PAUSED_PRICE_RE = re.compile(r"(?:(?<![<>])=+|[:：](?![^=]*=))\s*[【\[\(（]?\s*(暂停|停收|暂不收|不收|不要|拒收|不接)")
RANGE_RE = re.compile(
    r"(?P<prefix>US|USA|UK|EU|EUR|USD|GBP|HK|HKD|CAD|AUD|NZD|SAR|CHF|SGD|MYR|BRL|MXN|THB|PHP|JPY|ZAR|INR|IDR|TRY|PLN|DKK|SEK|NOK|CLP|COP|AED|ILS|TWD|KRW)?\s*"
    r"(?P<min>\d+(?:\.\d+)?\s*(?:[wW万])?)\s*(?:-|~|—|–|到|至)\s*"
    r"(?P<max>\d+(?:\.\d+)?\s*(?:[wW万])?)",
    re.IGNORECASE,
)
ABOVE_RE = re.compile(
    r"(?:(?:>\s*=|≥)\s*(?P<leading>\d+(?:\.\d+)?)|(?P<trailing>\d+(?:\.\d+)?)\s*(?:以上|\+))"
)
FIXED_DENOM_PRICE_RE = re.compile(
    r"面值\s*[:：]\s*(?P<denom>\d+(?:\.\d+)?)\s+(?P<rate>\d+(?:\.\d+)?)(?!\s*倍)"
)
MULTIPLIER_NUMBER_RE = re.compile(r"(?<![\d.])(?P<value>\d+(?:\.\d+)?)\s*(?:的\s*)?倍(?:数)?")
UNIT_NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?\s*[wW万]")
FACE_VALUE_RE = re.compile(r"(?P<first>\d+(?:\.\d+)?)(?:\s*/\s*(?P<second>\d+(?:\.\d+)?))+[^=]{0,8}面值")
FIXED_DENOM_RE = re.compile(r"(?P<values>\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)*)(?!\s*倍)")
FEEDBACK_TIME_RE = re.compile(r"\d+(?:\.\d+)?\s*[-~—–到至]\s*\d+(?:\.\d+)?\s*(?:min|mins|分钟|分)", re.IGNORECASE)
MARKET_RATE_RANGE_RE = re.compile(
    r"(?P<rate>\d+(?:\.\d+)?)\s*[（(]\s*"
    r"(?P<range>(?P<min>\d+(?:\.\d+)?)\s*[-~—–到至]\s*(?P<max>\d+(?:\.\d+)?))"
    r"(?P<inside>[^）)]*)[）)](?P<trailing>.*)$",
    re.IGNORECASE,
)
PENDING_SAME_RATE_RE = re.compile(
    r"图\s*(?:[/／]\s*)?密\s*同价\s*[:：]\s*[【\[\(（]?\s*(?P<rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
PENDING_DENOM_PREFIX_RE = re.compile(r"^\s*面值\s*[:：]", re.IGNORECASE)
BLOCK_REQUIREMENT_RE = re.compile(r"^\s*(?:备注|要求)\s*[:：]\s*(?P<text>.+)$", re.IGNORECASE)
QUESTION_NOTE_RE = re.compile(r"^\s*[【\[]\s*问\s*[】\]]\s*(?P<text>.+)$", re.IGNORECASE)
DECORATION_RE = re.compile(r"[💰🔥✅\ufe0f]")
SHORT_MARKET_PREFIXES = {
    "美": ("US", "USD"),
    "新": ("Singapore", "SGD"),
    "澳": ("Australia", "AUD"),
    "加": ("Canada", "CAD"),
    "墨": ("Mexico", "MXN"),
    "欧": ("EU", "EUR"),
    "英": ("UK", "GBP"),
}
MULTI_MARKET_LABELS = sorted(
    {
        "欧盟/英国",
        "迪拜阿联酋",
        "沙特阿拉伯",
        "印度尼西亚",
        "马来西亚",
        "哥伦比亚",
        "澳大利亚",
        "South Korea",
        "新加坡",
        "菲律宾",
        "加拿大",
        "土耳其",
        "墨西哥",
        "新西兰",
        "匈牙利",
        "以色列",
        "瑞 士",
        "日 本",
        "澳元",
        "瑞典",
        "挪威",
        "韩国",
        "瑞士",
        "丹麦",
        "波兰",
        "捷克",
        "香港",
        "南非",
        "阿联酋",
        "台湾",
        "沙特",
        "泰国",
        "印尼",
        "巴西",
        "印度",
        "日本",
        "智利",
        "EUR",
        "AUD",
        "US",
        "UK",
        "英国",
        "欧盟",
    },
    key=len,
    reverse=True,
)
MULTI_MARKET_SEGMENT_RE = re.compile(
    rf"(?P<label>{'|'.join(re.escape(item) for item in MULTI_MARKET_LABELS)})"
    r"(?P<brand>\s*(?:雷蛇|Razer|Steam|蒸汽))?\s*=+\s*(?P<rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
EXPLICIT_DUAL_TYPE_RATE_RE = re.compile(
    r"(?P<market>EUR|EU|欧盟|欧洲)\s*=+\s*(?P<physical_rate>\d+(?:\.\d+)?)\s*卡图"
    r"\s*代码\s*=*\s*(?P<code_rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
ROBLOX_MATRIX_LABELS = sorted(
    {
        "瑞典/挪威",
        "马来西亚",
        "墨西哥",
        "新西兰",
        "新加坡",
        "加拿大",
        "澳大利亚",
        "泰国",
        "巴西",
        "瑞典",
        "挪威",
        "欧盟",
        "美国",
        "英国",
        "USD",
        "EUR",
        "CAD",
        "AUD",
        "US",
        "UK",
    },
    key=len,
    reverse=True,
)
ROBLOX_MATRIX_RE = re.compile(
    rf"(?P<label>{'|'.join(re.escape(item) for item in ROBLOX_MATRIX_LABELS)})"
    r"(?:\s+(?P<currency>USD|EUR|CAD|AUD|GBP|THB|MXN|MYR|NZD|BRL|SGD|SEK|NOK))?"
    r"\s*=*\s*(?P<rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
PSN_MATRIX_LABELS = sorted(
    {
        "马来西亚",
        "保加利亚",
        "澳大利亚",
        "新西兰",
        "新加坡",
        "加拿大",
        "瑞典",
        "挪威",
        "台湾",
        "泰国",
        "丹麦",
        "巴西",
        "瑞士",
        "美国",
        "英国",
        "欧盟",
        "AUD",
        "CAD",
        "USD",
        "EUR",
        "US",
        "UK",
    },
    key=len,
    reverse=True,
)
PSN_MATRIX_RE = re.compile(
    rf"(?P<label>{'|'.join(re.escape(item) for item in PSN_MATRIX_LABELS)})"
    r"(?:\s+(?P<currency>USD|EUR|GBP|AUD|CAD|NZD|DKK|BRL|MYR|SEK|NOK|TWD|THB|BGN|SGD|CHF))?"
    r"\s*=*\s*(?P<rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
PSN_PURE_DIGITAL_RE = re.compile(
    r"(?:纯\s*数字|数字)\s*PSN\s*[=:]?\s*(?P<rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
PSN_SECOND_TIER_RE = re.compile(
    r"(?P<min>\d+(?:\.\d+)?)\s*(?:以上|\+)\s*(?P<rate>\d+(?:\.\d+)?)"
)
MULTI_RANGE_RATE_PAIR_RE = re.compile(
    r"(?<![\d.])(?P<denom>"
    r"\d+(?:\.\d+)?\s*(?:[wW万])?\s*(?:-|~|—|–|到|至)\s*\d+(?:\.\d+)?\s*(?:[wW万])?"
    r"|\d+(?:\.\d+)?\s*(?:[wW万])?"
    r")\s*=+\s*(?P<rate>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
ASK_WITHOUT_PRICE_RE = re.compile(r"=+\s*(?:ask|问)\s*$", re.IGNORECASE)


def standardize_brand(text: str | None) -> str:
    return normalize_brand(text)


def standardize_country_currency(country_text: str | None, currency_text: str | None = "") -> tuple[str, str]:
    country, currency = normalize_market(country_text, currency_text)
    if country and currency:
        return country, currency
    value = (country_text or "").strip()
    for prefix, market in SHORT_MARKET_PREFIXES.items():
        if re.match(rf"^{re.escape(prefix)}(?=$|[\s:：=])", value):
            return market
    code_prefixes = {
        "US": ("US", "USD"),
        "UK": ("UK", "GBP"),
        "EUR": ("EU", "EUR"),
        "AUD": ("Australia", "AUD"),
    }
    for prefix, market in code_prefixes.items():
        if re.match(rf"^{prefix}(?=\d|$|[\s:：=\-])", value, re.IGNORECASE):
            return market
    return "", ""


def standardize_frontend_type(text: str | None) -> str:
    value = (text or "").strip()
    lower = value.lower()
    if (
        any(token in value for token in ["代码/卡密", "卡密", "密卡", "电子", "纯代码", "代码"])
        or "code" in lower
        or re.search(r"(?<![a-z0-9])e-?card(?![a-z0-9])", lower)
    ):
        return "code"
    if any(token in value for token in ["卡图", "图卡", "横卡", "竖卡", "白卡", "散卡", "整卡", "实体卡", "物理卡", "卡片"]):
        return "physical"
    if "physical" in lower:
        return "physical"
    return ""


def standardize_subtype(text: str | None, frontend_type: str = "") -> str:
    value = (text or "").strip()
    lower = value.lower()
    if any(token in value for token in ["代码/卡密", "卡密", "密卡"]):
        return "代码/卡密"
    if "竖版卡" in value or "vertical" in lower:
        return "竖卡"
    if "电子" in value or re.search(r"(?<![a-z0-9])e-?(?:code|card)(?![a-z0-9])", lower) or any(
        token in lower for token in ["digital", "email delivery", "email card"]
    ):
        return "电子卡"
    if "整卡/散卡" in value or "整卡／散卡" in value:
        return "整卡/散卡"
    if "散卡" in value:
        return "散卡"
    if "整卡" in value:
        return "整卡"
    if "横白" in value:
        return "横白"
    for token in ["横卡", "竖卡", "白卡"]:
        if token in value:
            return token
    if any(token in value for token in ["卡图", "图卡", "卡片图片", "卡图图片", "实体图", "图片", "物理卡", "横版卡"]):
        return "卡图"
    if "纯代码" in value or "代码" in value or "code" in lower or "pin" in lower:
        return "代码/卡密"
    if "截图" in value:
        return "待确认"
    if "实体卡" in value or "物理卡" in value or "卡片" in value:
        return "普通物理卡"
    if "图" in value:
        return "卡图"
    if "密" in value:
        return "代码/卡密"
    if frontend_type == "code":
        return "代码/卡密"
    if frontend_type == "physical":
        return "普通物理卡"
    return ""


def standardize_processing_method(text: str | None) -> str:
    value = (text or "").strip()
    if "慢刷" in value or "慢网" in value:
        return "slow_process"
    if "快刷" in value or "快网" in value:
        return "fast_process"
    if "快卡" in value or "快加" in value:
        return "fast_card"
    return value if value in METHOD_LABELS else "fast_card"


def standardize_status(text: str | None) -> str:
    value = (text or "").strip()
    if "暂停" in value or "停收" in value or "暂不收" in value:
        return "paused"
    if "不收" in value or "不要" in value or "拒收" in value or "不接" in value:
        return "unavailable"
    if "发前问" in value or "提前问" in value or "问" in value:
        return "ask_first"
    if "锁卡" in value or "拒付" in value or "不结算" in value:
        return "warning"
    return value if value in {"active", "ask_first", "paused", "unavailable", "warning"} else "active"


def parse_quote_text(
    supplier_group: str,
    source_text: str,
    default_expire_hours: float = 24,
    created_by: str = "",
    default_brand: str = "",
    default_market: str = "",
    default_processing_method: str = "",
    default_multiplier: float | None = None,
    default_subtype: str = "",
    ignored_items: list[str] | None = None,
) -> list[dict[str, Any]]:
    if _should_use_apple_block_parser(source_text, default_brand):
        return parse_apple_itunes_blocks(
            supplier_group=supplier_group,
            source_text=source_text,
            default_expire_hours=default_expire_hours,
            created_by=created_by,
            default_market=default_market,
            default_processing_method=default_processing_method,
            default_multiplier=default_multiplier,
            default_subtype=default_subtype,
        )

    rows: list[dict[str, Any]] = []
    context = _empty_context()
    pending_quote_context: dict[str, Any] | None = None
    block_row_indexes: list[int] = []
    pending_psn_eur_indexes: list[int] = []
    pending_psn_country_lines: list[str] = []
    pending_psn_country_source_lines: list[str] = []
    default_context = _default_context(
        brand=default_brand,
        market=default_market,
        processing_method=default_processing_method,
        multiplier=default_multiplier,
        subtype=default_subtype,
    )

    for line_no, raw_line in enumerate(source_text.splitlines(), start=1):
        source_line = raw_line.strip()
        line = _normalize_input_line(source_line)
        if not line:
            continue

        if pending_psn_eur_indexes and (
            pending_psn_country_lines or _starts_psn_eur_country_list(line)
        ):
            pending_psn_country_lines.append(line)
            pending_psn_country_source_lines.append(source_line)
            if not re.search(r"[）)]", line):
                continue
            country_text = " ".join(pending_psn_country_lines)
            country_variants = eur_country_variants(country_text)
            if country_variants:
                block_row_indexes = _expand_psn_eur_rows(
                    rows,
                    pending_psn_eur_indexes,
                    country_variants,
                    pending_psn_country_source_lines,
                    block_row_indexes,
                )
            pending_psn_eur_indexes = []
            pending_psn_country_lines = []
            pending_psn_country_source_lines = []
            continue
        if pending_psn_eur_indexes:
            pending_psn_eur_indexes = []

        if _is_separator_line(line):
            pending_quote_context = None
            block_row_indexes = []
            continue

        if ASK_WITHOUT_PRICE_RE.search(line):
            if ignored_items is not None:
                ignored_items.append(f"{source_line}：无明确价格，已忽略。")
            continue

        block_requirement = _extract_block_requirement(line)
        if block_requirement:
            context["requirements"] = _append_text(context.get("requirements"), block_requirement)
            if pending_quote_context is not None:
                pending_quote_context["requirements"] = _append_text(
                    pending_quote_context.get("requirements"), block_requirement
                )
            for row_index in block_row_indexes:
                rows[row_index]["requirements"] = _append_text(rows[row_index].get("requirements"), block_requirement)
            continue

        question_requirement = _extract_question_requirement(line)
        if question_requirement:
            context["requirements"] = _append_text(context.get("requirements"), question_requirement)
            for row_index in block_row_indexes:
                rows[row_index]["requirements"] = _append_text(
                    rows[row_index].get("requirements"), question_requirement
                )
            continue

        if _is_comment_line(line):
            comment_text = _strip_comment_prefix(line)
            if line.lstrip().startswith("#") and _has_price(comment_text):
                line = comment_text
            else:
                title_context = parse_title_context(comment_text)
                if title_context.get("brand"):
                    sticky_context = {
                        key: context.get(key)
                        for key in ("processing_method", "multiplier", "requirements", "feedback_note")
                        if context.get(key)
                    }
                    context = _empty_context()
                    context.update(sticky_context)
                    context.update(
                        {key: value for key, value in title_context.items() if value not in (None, "")}
                    )
                    continue
                context["requirements"] = _append_text(context.get("requirements"), comment_text)
                for row_index in block_row_indexes:
                    rows[row_index]["requirements"] = _append_text(
                        rows[row_index].get("requirements"), comment_text
                    )
                continue

        amazon_dual_type_segments = _amazon_dual_type_segments(line, context, default_context)
        if amazon_dual_type_segments:
            start_index = len(rows)
            for segment in amazon_dual_type_segments:
                rows.extend(
                    parse_quote_line_rows(
                        supplier_group=supplier_group,
                        line=segment,
                        default_expire_hours=default_expire_hours,
                        created_by=created_by,
                        context=context,
                        default_context=default_context,
                        line_no=line_no,
                        source_line=source_line,
                        parse_note_prefix="Amazon 卡图/代码双价格拆分",
                    )
                )
            block_row_indexes.extend(range(start_index, len(rows)))
            pending_quote_context = None
            continue

        multi_range_segments = _multi_range_rate_segments(line)
        if len(multi_range_segments) > 1:
            start_index = len(rows)
            for segment in multi_range_segments:
                generated_rows = parse_quote_line_rows(
                    supplier_group=supplier_group,
                    line=segment["line"],
                    default_expire_hours=default_expire_hours,
                    created_by=created_by,
                    context=context,
                    default_context=default_context,
                    line_no=line_no,
                    source_line=source_line,
                    parse_note_prefix="由同一行多个范围报价拆分",
                )
                for row in generated_rows:
                    row["requirements"] = _append_text(
                        row.get("requirements"), segment.get("requirements")
                    )
                rows.extend(generated_rows)
            block_row_indexes.extend(range(start_index, len(rows)))
            pending_quote_context = None
            continue

        loose_quote_segments = _loose_quote_segments(line, context, default_context)
        if loose_quote_segments:
            title_updates = parse_title_context(line)
            for key in (
                "country",
                "currency",
                "frontend_type",
                "subtype",
                "processing_method",
                "feedback_note",
                "multiplier",
                "quote_same_type",
            ):
                if title_updates.get(key) not in (None, ""):
                    context[key] = title_updates[key]
            start_index = len(rows)
            for segment in loose_quote_segments:
                rows.extend(
                    parse_quote_line_rows(
                        supplier_group=supplier_group,
                        line=segment,
                        default_expire_hours=default_expire_hours,
                        created_by=created_by,
                        context=context,
                        default_context=default_context,
                        line_no=line_no,
                        source_line=source_line,
                        parse_note_prefix="由无等号范围/面值报价解析",
                        allow_unbounded=True,
                    )
                )
            block_row_indexes.extend(range(start_index, len(rows)))
            pending_quote_context = None
            continue

        dual_type_segments = _explicit_dual_type_segments(line)
        if dual_type_segments:
            start_index = len(rows)
            for segment in dual_type_segments:
                rows.extend(
                    parse_quote_line_rows(
                        supplier_group=supplier_group,
                        line=segment,
                        default_expire_hours=default_expire_hours,
                        created_by=created_by,
                        context=context,
                        default_context=default_context,
                        line_no=line_no,
                        source_line=source_line,
                        parse_note_prefix="同一市场卡图/代码不同价拆分",
                        allow_unbounded=True,
                    )
                )
            block_row_indexes.extend(range(start_index, len(rows)))
            pending_quote_context = None
            continue

        matrix_segments, matrix_note = _roblox_matrix_segments(line, context, default_context)
        if matrix_segments:
            start_index = len(rows)
            for segment in matrix_segments:
                rows.extend(
                    parse_quote_line_rows(
                        supplier_group=supplier_group,
                        line=segment,
                        default_expire_hours=default_expire_hours,
                        created_by=created_by,
                        context=context,
                        default_context=default_context,
                        line_no=line_no,
                        source_line=source_line,
                        parse_note_prefix="由 Roblox 国家/币种价格矩阵拆分",
                        allow_unbounded=True,
                    )
                )
            block_row_indexes.extend(range(start_index, len(rows)))
            if matrix_note:
                context["requirements"] = _append_text(context.get("requirements"), matrix_note)
                for row_index in block_row_indexes:
                    rows[row_index]["requirements"] = _append_text(
                        rows[row_index].get("requirements"), matrix_note
                    )
            pending_quote_context = None
            continue

        psn_segments = _psn_matrix_segments(line, context, default_context)
        if psn_segments:
            start_index = len(rows)
            for segment in psn_segments:
                generated_rows = parse_quote_line_rows(
                    supplier_group=supplier_group,
                    line=segment["line"],
                    default_expire_hours=default_expire_hours,
                    created_by=created_by,
                    context=context,
                    default_context=default_context,
                    line_no=line_no,
                    source_line=source_line,
                    parse_note_prefix="由 PSN 国家/币种价格矩阵拆分",
                    allow_unbounded=True,
                )
                for row in generated_rows:
                    row["requirements"] = _append_text(
                        row.get("requirements"), segment.get("requirements")
                    )
                rows.extend(generated_rows)
            new_indexes = list(range(start_index, len(rows)))
            block_row_indexes.extend(new_indexes)
            if psn_segments and all(segment.get("market") == ("EU", "EUR") for segment in psn_segments):
                pending_psn_eur_indexes = new_indexes
            pending_quote_context = None
            continue

        multi_market_segments = _split_multi_market_quote_segments(line)
        if len(multi_market_segments) > 1:
            start_index = len(rows)
            for segment in multi_market_segments:
                segment_allow_unbounded = _is_special_unbounded_quote(segment, context, default_context)
                rows.extend(
                    parse_quote_line_rows(
                        supplier_group=supplier_group,
                        line=segment,
                        default_expire_hours=default_expire_hours,
                        created_by=created_by,
                        context=context,
                        default_context=default_context,
                        line_no=line_no,
                        source_line=source_line,
                        parse_note_prefix="由同一行多国家报价拆分",
                        allow_unbounded=segment_allow_unbounded,
                    )
                )
            block_row_indexes.extend(range(start_index, len(rows)))
            pending_quote_context = None
            continue

        pending_denom = _parse_pending_denom_line(line)
        if pending_quote_context is not None and pending_denom:
            pending_context = dict(pending_quote_context.get("context") or context)
            pending_context["country"] = pending_quote_context["country"]
            pending_context["currency"] = pending_quote_context["currency"]
            pending_context["requirements"] = _append_text(
                pending_context.get("requirements"), pending_quote_context.get("requirements")
            )
            synthetic_line = _pending_quote_synthetic_line(pending_quote_context, pending_denom)
            combined_source_line = f"{pending_quote_context['source_line']}\n{source_line}"
            generated_rows = parse_quote_line_rows(
                supplier_group=supplier_group,
                line=synthetic_line,
                default_expire_hours=default_expire_hours,
                created_by=created_by,
                context=pending_context,
                default_context=default_context,
                line_no=pending_quote_context["line_no"],
                source_line=combined_source_line,
                parse_note_prefix="由两行组合报价合并解析",
            )
            start_index = len(rows)
            rows.extend(generated_rows)
            block_row_indexes.extend(range(start_index, len(rows)))
            pending_quote_context = None
            continue

        if pending_denom:
            if pending_denom.get("multiplier") is not None:
                context["multiplier"] = pending_denom["multiplier"]
            pending_quote_context = None
            continue

        pending_rate = _parse_pending_rate_line(line)
        if pending_rate:
            pending_quote_context = {
                **pending_rate,
                "source_line": source_line,
                "line_no": line_no,
                "requirements": context.get("requirements", ""),
                "context": dict(context),
            }
            continue

        pending_quote_context = None

        allow_unbounded = _is_special_unbounded_quote(line, context, default_context)
        if not _has_price(line) and not allow_unbounded:
            title_context = parse_title_context(line)
            if _is_plain_requirement_line(line) and not title_context.get("brand"):
                context["requirements"] = _append_text(context.get("requirements"), line)
                for row_index in block_row_indexes:
                    rows[row_index]["requirements"] = _append_text(rows[row_index].get("requirements"), line)
            elif title_context:
                if title_context.get("brand"):
                    sticky_context = {
                        key: context.get(key)
                        for key in ("processing_method", "multiplier", "requirements", "feedback_note")
                        if context.get(key)
                    }
                    context = _empty_context()
                    context.update(sticky_context)
                context.update({key: value for key, value in title_context.items() if value not in (None, "")})
            context_denom = _context_denom_from_line(line)
            if context_denom:
                context["denom_min"], context["denom_max"] = context_denom
            continue

        generated_rows = parse_quote_line_rows(
            supplier_group=supplier_group,
            line=line,
            default_expire_hours=default_expire_hours,
            created_by=created_by,
            context=context,
            default_context=default_context,
            line_no=line_no,
            source_line=source_line,
            allow_unbounded=allow_unbounded,
        )
        start_index = len(rows)
        rows.extend(generated_rows)
        block_row_indexes.extend(range(start_index, len(rows)))

    return rows


def _should_use_apple_block_parser(source_text: str, default_brand: str) -> bool:
    brand = standardize_brand(source_text) or normalize_brand(default_brand)
    if brand != "Apple":
        return False
    lines = [_normalize_input_line(line) for line in source_text.splitlines()]
    if any(_is_apple_bracket_market_subtype_quote(line) for line in lines):
        return True
    if any(_apple_bracket_title_context(line) for line in lines):
        return True
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if re.match(r"^(?:面值|倍数|整卡卡图)[:：]", compact):
            roles = classify_numbers_in_line(line)
            if roles["multiplier"] is not None or roles["ranges"] or roles["open_ranges"]:
                return True
    return False


def parse_apple_itunes_blocks(
    supplier_group: str,
    source_text: str,
    default_expire_hours: float = 24,
    created_by: str = "",
    default_market: str = "",
    default_processing_method: str = "",
    default_multiplier: float | None = None,
    default_subtype: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in _split_apple_quote_blocks(source_text):
        rows.extend(
            _parse_apple_quote_block(
                supplier_group=supplier_group,
                block=block,
                default_expire_hours=default_expire_hours,
                created_by=created_by,
                default_market=default_market,
                default_processing_method=default_processing_method,
                default_multiplier=default_multiplier,
                default_subtype=default_subtype,
            )
        )
    return rows


def _split_apple_quote_blocks(source_text: str) -> list[list[dict[str, Any]]]:
    blocks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(source_text.splitlines(), start=1):
        source_line = raw_line.strip()
        line = _normalize_input_line(source_line)
        if not line or _is_separator_line(line):
            if current:
                blocks.append(current)
                current = []
            continue
        current.append({"line_no": line_no, "source_line": source_line, "line": line})
    if current:
        blocks.append(current)
    return blocks


def _parse_apple_quote_block(
    supplier_group: str,
    block: list[dict[str, Any]],
    default_expire_hours: float,
    created_by: str,
    default_market: str,
    default_processing_method: str,
    default_multiplier: float | None,
    default_subtype: str,
) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    constraint_values: dict[str, list[Any]] = {
        "denom": [],
        "multiplier": [],
        "subtypes": [],
        "processing_method": [],
        "feedback_note": [],
    }
    block_requirements = ""
    block_title_markets: list[tuple[str, str]] = []
    active_plain_title_markets: list[tuple[str, str]] = []
    active_plain_title_subtypes: list[str] = []

    for item in block:
        title_context = _apple_bracket_title_context(item["line"])
        if title_context:
            block_title_markets = title_context["markets"] or block_title_markets
            block_requirements = _append_text(
                block_requirements,
                title_context.get("requirements"),
            )
            continue

        draft = _apple_price_draft(item)
        if draft:
            if active_plain_title_markets and not draft["country_targets"]:
                draft["country_targets"] = list(active_plain_title_markets)
            if active_plain_title_subtypes and not draft["subtypes"]:
                draft["subtypes"] = list(active_plain_title_subtypes)
            drafts.append(draft)
            continue

        plain_title_context = _apple_plain_title_context(item["line"])
        if plain_title_context:
            active_plain_title_markets = plain_title_context["markets"]
            active_plain_title_subtypes = plain_title_context["subtypes"]
            continue

        constraint = _apple_constraint_from_line(item["line"])
        for key, value in constraint.items():
            if value in (None, "", []):
                continue
            constraint_values[key].append(value)
            if drafts:
                drafts[-1]["following_constraints"][key] = value

        requirement = _apple_block_requirement(item["line"])
        if requirement:
            block_requirements = _append_text(block_requirements, requirement)

    if not drafts:
        return []

    common_constraints = {
        key: _single_distinct_value(values)
        for key, values in constraint_values.items()
    }
    explicit_subtypes = [draft["subtypes"] for draft in drafts if draft.get("subtypes")]
    block_subtypes = common_constraints.get("subtypes") or _single_distinct_value(explicit_subtypes)
    explicit_methods = [draft["processing_method"] for draft in drafts if draft.get("processing_method")]
    block_method = common_constraints.get("processing_method") or _single_distinct_value(explicit_methods)
    explicit_feedback = [draft["feedback_note"] for draft in drafts if draft.get("feedback_note")]
    block_feedback = common_constraints.get("feedback_note") or _single_distinct_value(explicit_feedback)

    explicit_markets = []
    for draft in drafts:
        explicit_markets.extend(draft.get("country_targets") or [])
    block_market = _single_distinct_value(explicit_markets)
    default_country, default_currency = split_market_value(default_market)

    rows: list[dict[str, Any]] = []
    for draft in drafts:
        following = draft["following_constraints"]
        fallback_denom = following.get("denom") or common_constraints.get("denom")
        denoms = draft.get("denoms") or ([fallback_denom] if fallback_denom else [None])
        multiplier = (
            draft.get("multiplier")
            if draft.get("multiplier") is not None
            else following.get("multiplier")
            if following.get("multiplier") is not None
            else common_constraints.get("multiplier")
            if common_constraints.get("multiplier") is not None
            else default_multiplier
        )
        subtypes = (
            draft.get("subtypes")
            or following.get("subtypes")
            or block_subtypes
            or ([standardize_subtype(default_subtype)] if default_subtype else None)
            or ["卡图", "代码/卡密"]
        )
        country_targets = (
            draft.get("country_targets")
            or block_title_markets
            or ([block_market] if block_market else [])
        )
        if not country_targets and default_country and default_currency:
            country_targets = [(default_country, default_currency)]
        method = (
            draft.get("processing_method")
            or following.get("processing_method")
            or block_method
            or default_processing_method
            or "fast_card"
        )
        feedback_note = (
            draft.get("feedback_note")
            or following.get("feedback_note")
            or block_feedback
            or ""
        )

        for denom in denoms:
            for country, currency in country_targets or [("", "")]:
                for subtype in subtypes:
                    rows.extend(
                        _build_apple_block_rows(
                            supplier_group=supplier_group,
                            draft=draft,
                            country=country,
                            currency=currency,
                            subtype=subtype,
                            denom=denom,
                            multiplier=multiplier,
                            processing_method=method,
                            feedback_note=feedback_note,
                            requirements=_append_text(
                                block_requirements,
                                draft.get("requirements"),
                            ),
                            default_expire_hours=default_expire_hours,
                            created_by=created_by,
                        )
                    )
    return rows


def _apple_bracket_title_context(line: str) -> dict[str, Any] | None:
    match = re.match(r"^\s*【\s*(?P<title>[^】]+?)\s*】(?P<suffix>.*)$", line)
    if not match or _is_apple_bracket_market_subtype_quote(line):
        return None
    title = match.group("title")
    if standardize_brand(title):
        return None
    markets = _apple_country_targets(title)
    if not markets:
        return None
    return {
        "markets": markets,
        "requirements": _normalize_hash_requirements(match.group("suffix")),
    }


def _apple_plain_title_context(line: str) -> dict[str, Any] | None:
    roles = classify_numbers_in_line(line)
    if (
        roles["supplier_rate_candidates"]
        or roles["ranges"]
        or roles["open_ranges"]
        or roles["fixed_denom"] is not None
    ):
        return None
    markets = _apple_country_targets(line)
    subtypes = _apple_explicit_subtypes(line)
    if not markets or not subtypes:
        return None
    return {"markets": markets, "subtypes": subtypes}


def _is_apple_bracket_market_subtype_quote(line: str) -> bool:
    match = re.match(r"^\s*【\s*(?P<title>[^】]+?)\s*】(?P<suffix>.+)$", line)
    if not match or standardize_brand(match.group("title")):
        return False
    markets = _apple_country_targets(match.group("title"))
    roles = classify_numbers_in_line(line)
    return bool(markets and roles["supplier_rate_candidates"] and roles["ranges"])


def _apple_price_draft(item: dict[str, Any]) -> dict[str, Any] | None:
    line = item["line"]
    roles = classify_numbers_in_line(line)
    candidates = roles["supplier_rate_candidates"]
    if not candidates:
        return None

    country_targets = _apple_country_targets(line)
    subtypes = _apple_explicit_subtypes(line)
    rate_candidate = candidates[0]
    denom_options = extract_denom_options(line, rate_candidate["span"])
    denoms = list(
        dict.fromkeys((option[0], option[1]) for option in denom_options)
    )
    if not denoms:
        role_denom = _apple_denom_from_roles(roles)
        if role_denom is not None:
            denoms = [role_denom]
    if not country_targets and not subtypes and not denoms:
        return None

    return {
        **item,
        "supplier_rate": rate_candidate["value"],
        "country_targets": country_targets,
        "subtypes": subtypes,
        "denoms": denoms,
        "multiplier": roles["multiplier"],
        "requirements": _append_text(
            _apple_inline_requirements(line),
            _apple_inline_note_requirements(line),
        ),
        "processing_method": _explicit_processing_method(line),
        "feedback_note": extract_feedback_note(line),
        "status": standardize_status(line),
        "following_constraints": {},
    }


def _apple_constraint_from_line(line: str) -> dict[str, Any]:
    roles = classify_numbers_in_line(line)
    constraint: dict[str, Any] = {}
    denom = _apple_denom_from_roles(roles)
    if denom is not None:
        constraint["denom"] = denom
    if roles["multiplier"] is not None:
        constraint["multiplier"] = roles["multiplier"]
    subtypes = _apple_explicit_subtypes(line)
    if subtypes:
        constraint["subtypes"] = subtypes
    method = _explicit_processing_method(line)
    if method:
        constraint["processing_method"] = method
    feedback_note = extract_feedback_note(line)
    if feedback_note:
        constraint["feedback_note"] = feedback_note
    return constraint


def _apple_denom_from_roles(roles: dict[str, Any]) -> tuple[float, float | None] | None:
    if roles["ranges"]:
        first = roles["ranges"][0]
        return first["min"], first["max"]
    if roles["open_ranges"]:
        return roles["open_ranges"][0]["min"], None
    if roles["fixed_denom"] is not None:
        return roles["fixed_denom"], roles["fixed_denom"]
    return None


def _apple_country_targets(line: str) -> list[tuple[str, str]]:
    combined = _combined_country_variants(line)
    if combined:
        return combined
    eur_variants = eur_country_variants(line)
    if eur_variants:
        return eur_variants
    country, currency = standardize_country_currency(line)
    return [(country, currency)] if country and currency else []


def _apple_explicit_subtypes(line: str) -> list[str]:
    quote_text = line.split("#", 1)[0]
    roles = classify_numbers_in_line(quote_text)
    if roles["supplier_rate_candidates"]:
        rate_end = roles["supplier_rate_candidates"][0]["span"][1]
        trailing_subtypes = _apple_subtypes_from_text(quote_text[rate_end:])
        if trailing_subtypes:
            return trailing_subtypes
    return _apple_subtypes_from_text(quote_text)


def _apple_subtypes_from_text(text: str) -> list[str]:
    text = text.replace("审图", "")
    compact = re.sub(r"\s+", "", text)
    lower = text.lower()
    if _has_image_and_code_same_price(text) or _card_image_secret_pair(text):
        return ["卡图", "代码/卡密"]
    if "电子" in compact or re.search(r"(?<![a-z0-9])e-?card(?![a-z0-9])", lower):
        return ["电子卡"]
    if "竖卡" in compact or "竖版卡" in compact or "vertical" in lower:
        return ["竖卡"]
    if "整卡/散卡" in compact or "整卡／散卡" in compact:
        return ["整卡/散卡"]
    if "整卡" in compact:
        return ["整卡"]
    if "散卡" in compact:
        return ["散卡"]
    if any(token in compact for token in ["代码", "卡密", "纯代码", "密卡"]):
        return ["代码/卡密"]
    if any(token in compact for token in ["横白", "横卡", "白卡", "卡图", "图卡"]):
        return [standardize_subtype(compact)]
    if re.search(r"(?<![图/／])图(?!\s*[/／]?\s*密)", compact):
        return ["卡图"]
    if re.search(r"(?<!图)密", compact):
        return ["代码/卡密"]
    return []


def _apple_block_requirement(line: str) -> str:
    requirement = _extract_block_requirement(line)
    if requirement:
        return _normalize_hash_requirements(requirement)
    if line.lstrip().startswith("#") or _is_plain_requirement_line(line) or "不拿" in line:
        return _normalize_hash_requirements(line)
    return ""


def _apple_inline_requirements(line: str) -> str:
    if "#" not in line:
        return ""
    requirement = _normalize_hash_requirements(line.split("#", 1)[1])
    if re.fullmatch(r"\d+\s*(?:的\s*)?倍(?:数)?", requirement):
        return ""
    return requirement


def _apple_inline_note_requirements(line: str) -> str:
    notes = []
    if "审图" in line:
        notes.append("审图")
    if "连卡问" in line:
        notes.append("连卡问")
    return "；".join(notes)


def _normalize_hash_requirements(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s+#(?=\d)", "；", cleaned, count=1)
    cleaned = re.sub(r"#(?=\d)", "/", cleaned)
    cleaned = cleaned.replace("#", "；")
    cleaned = re.sub(r"[；;]+", "；", cleaned)
    cleaned = re.sub(r"\s*；\s*", "；", cleaned)
    return _clean_requirement_fragment(cleaned)


def _single_distinct_value(values: list[Any]) -> Any:
    distinct: list[Any] = []
    for value in values:
        if value not in distinct:
            distinct.append(value)
    return distinct[0] if len(distinct) == 1 else None


def _build_apple_block_rows(
    supplier_group: str,
    draft: dict[str, Any],
    country: str,
    currency: str,
    subtype: str,
    denom: tuple[float, float | None] | None,
    multiplier: float | None,
    processing_method: str,
    feedback_note: str,
    requirements: str,
    default_expire_hours: float,
    created_by: str,
) -> list[dict[str, Any]]:
    denom_text = ""
    if denom:
        minimum, maximum = denom
        if maximum is None:
            denom_text = f"{format(minimum, 'g')}以上"
        elif minimum == maximum:
            denom_text = format(minimum, "g")
        else:
            denom_text = f"{format(minimum, 'g')}-{format(maximum, 'g')}"
    multiplier_text = f" {format(multiplier, 'g')}倍数" if multiplier is not None else ""
    status_text = " 发前问" if draft["status"] == "ask_first" else ""
    synthetic = (
        f"Apple {country} {currency} {denom_text} {subtype}="
        f"{decimal_text(draft['supplier_rate'])}{multiplier_text}{status_text}"
    ).strip()
    generated = parse_quote_line_rows(
        supplier_group=supplier_group,
        line=synthetic,
        default_expire_hours=default_expire_hours,
        created_by=created_by,
        context=_empty_context(),
        default_context=_default_context(brand="Apple"),
        line_no=draft["line_no"],
        source_line=draft["source_line"],
        parse_note_prefix="Apple/iTunes 分段两遍解析；段内后置条件已回填",
        allow_unbounded=denom is None,
    )
    generated = generated[:1]
    for row in generated:
        frontend_type = _frontend_type_for_subtype(subtype) or "physical"
        row.update(
            {
                "brand": "Apple",
                "country": country,
                "currency": currency,
                "frontend_type": frontend_type,
                "subtype": subtype,
                "raw_card_subtype": subtype,
                "normalized_card_subtype": normalize_card_subtype_for_brand(
                    "Apple", subtype, frontend_type
                ),
                "processing_method": processing_method,
                "feedback_note": feedback_note,
                "multiplier": multiplier,
                "denom_min": denom[0] if denom else None,
                "denom_max": denom[1] if denom else None,
                "range_type": range_type_for_values(
                    denom[0] if denom else None,
                    denom[1] if denom else None,
                ),
                "supplier_rate": draft["supplier_rate"],
                "status": draft["status"],
                "source_text": draft["source_line"],
                "source_line": draft["source_line"],
                "line_no": draft["line_no"],
                "requirements": _append_text(row.get("requirements"), requirements),
            }
        )
    return generated


def parse_quote_line(
    supplier_group: str,
    line: str,
    default_expire_hours: float = 24,
    created_by: str = "",
) -> dict[str, Any]:
    allow_unbounded = _is_special_unbounded_quote(line, _empty_context(), _empty_context())
    if not _has_price(line) and not allow_unbounded:
        return {}
    rows = parse_quote_line_rows(
        supplier_group=supplier_group,
        line=line,
        default_expire_hours=default_expire_hours,
        created_by=created_by,
        context=_empty_context(),
        line_no=1,
        allow_unbounded=allow_unbounded,
    )
    return rows[0] if rows else {}


def parse_quote_line_rows(
    supplier_group: str,
    line: str,
    default_expire_hours: float = 24,
    created_by: str = "",
    context: dict[str, Any] | None = None,
    default_context: dict[str, Any] | None = None,
    line_no: int = 1,
    source_line: str | None = None,
    parse_note_prefix: str = "",
    allow_unbounded: bool = False,
) -> list[dict[str, Any]]:
    if not _has_price(line) and not (allow_unbounded and _has_explicit_numeric_price(line)):
        return []

    context = context or _empty_context()
    default_context = default_context or _empty_context()
    now = datetime.now().replace(microsecond=0)
    expires_at = _expires_at(line, now, default_expire_hours)

    explicit_multiplier = extract_multiplier(line)
    supplier_rate, rate_span = extract_supplier_rate(line, [], explicit_multiplier)
    denom_options = extract_denom_options(line, rate_span)
    if not denom_options and context.get("denom_min") is not None:
        denom_options = [
            (
                float(context["denom_min"]),
                float(context["denom_max"]) if context.get("denom_max") is not None else None,
                None,
                "继承上下文面额范围",
            )
        ]
    primary_range_span = denom_options[0][2] if denom_options else None
    line_brand = standardize_brand(line)
    line_country, line_currency = standardize_country_currency(line)
    line_method = _explicit_processing_method(line)
    line_feedback_note = extract_feedback_note(line)
    line_status = standardize_status(line)
    card_count_multiplier, multiplier_note = extract_card_count_multiplier(line, explicit_multiplier)
    line_multiplier = explicit_multiplier if explicit_multiplier is not None else card_count_multiplier

    brand = line_brand or context.get("brand") or default_context.get("brand") or ""
    country = line_country or context.get("country") or default_context.get("country") or ""
    currency = line_currency or context.get("currency") or default_context.get("currency") or ""
    market_default_note = ""
    if not country and not currency and brand in DEFAULT_US_MARKET_BRANDS:
        country, currency = "US", "USD"
        market_default_note = "长尾零售卡未写地区/币种，默认美国 / US / USD"
    country_targets = [(country, currency)]
    country_split_note = ""
    combined_country_targets = _combined_country_variants(line)
    if combined_country_targets:
        country_targets = combined_country_targets
        country_split_note = "由组合国家比爱奥拆分"
    elif not (line_country or line_currency) and context.get("country_variants"):
        country_targets = list(context["country_variants"])
        country_split_note = "由欧盟标题中的具体国家拆分"
    method = line_method or context.get("processing_method") or default_context.get("processing_method") or "fast_card"
    feedback_note = line_feedback_note or context.get("feedback_note") or ""
    multiplier = (
        line_multiplier
        if line_multiplier is not None
        else context.get("multiplier")
        if context.get("multiplier") is not None
        else default_context.get("multiplier")
    )
    requirements = _append_text(context.get("requirements"), extract_requirements(line, line_status))
    requirements = _append_text(requirements, extract_market_rate_requirements(line))
    requirements = _append_text(requirements, extract_bracket_requirements(line))
    denom_note = "；".join(dict.fromkeys(option[3] for option in denom_options if option[3]))
    requirements = _append_text(requirements, denom_note)
    requirements = _append_text(requirements, _extract_bracket_quote_trailing_requirement(line, primary_range_span))
    requirements = _append_text(requirements, _extract_unbounded_bracket_trailing_requirement(line, primary_range_span))

    subtype_candidates, subtype_note = extract_subtype_candidates(line, primary_range_span, rate_span)
    if not subtype_candidates:
        if context.get("quote_same_type") == "image_and_code_same_price":
            subtype_candidates = ["卡图", "代码/卡密"]
            subtype_note = "继承标题图密同价规则"
        elif brand in DEFAULT_SAME_RATE_BRANDS:
            subtype_candidates = ["卡图", "代码/卡密"]
            subtype_note = f"{brand} 未区分图/密，按默认图密同价拆分"
        elif brand == "PSN":
            subtype_candidates = ["卡图", "代码/卡密"]
            subtype_note = "PSN 未区分图/密，按默认图密同价拆分"
        else:
            inherited = context.get("subtype") or default_context.get("subtype") or ""
            if inherited:
                subtype_candidates = [inherited]
            elif brand:
                subtype_candidates = ["卡图", "代码/卡密"]
                subtype_note = f"{brand} 未明确细分，按全品牌默认图密同价拆分"
            else:
                subtype_candidates = ["待确认"]

    subtype_candidates, brand_subtype_note = _apply_brand_subtype_rules(
        brand,
        line,
        subtype_candidates,
    )
    subtype_note = _append_text(subtype_note, brand_subtype_note)

    split_note = "图/密 拆分为卡图和代码/卡密两条报价" if _has_card_image_and_secret(subtype_candidates) else ""
    rows = []
    for subtype in subtype_candidates:
        clean_subtype = standardize_subtype(subtype) or subtype or "待确认"
        frontend_type = _frontend_type_for_subtype(clean_subtype) or standardize_frontend_type(line) or context.get("frontend_type") or "physical"
        for target_country, target_currency in country_targets:
            row_country = target_country or country
            row_currency = target_currency or currency
            for denom_min, denom_max, _, _ in denom_options or [(None, None, None, "")]:
                confidence, confidence_notes = _score_confidence(
                    brand=brand,
                    country=row_country,
                    currency=row_currency,
                    frontend_type=frontend_type,
                    subtype=clean_subtype,
                    denom_min=denom_min,
                    supplier_rate=supplier_rate,
                    context=context,
                    line_brand=line_brand,
                    line_country=line_country,
                    line_currency=line_currency,
                    denom_optional=allow_unbounded,
                )
                parse_note = "；".join(
                    note
                    for note in [
                        parse_note_prefix,
                        _inherit_note(context, line_brand, line_country, line_currency),
                        market_default_note,
                        country_split_note,
                        subtype_note,
                        multiplier_note,
                        split_note,
                        *confidence_notes,
                    ]
                    if note
                )

                rows.append(
                    {
                        "supplier_group": supplier_group.strip(),
                        "source_text": source_line or line,
                        "source_line": source_line or line,
                        "line_no": line_no,
                        "parse_note": parse_note,
                        "brand": brand,
                        "country": row_country,
                        "currency": row_currency,
                        "frontend_type": frontend_type,
                        "subtype": clean_subtype,
                        "raw_card_subtype": clean_subtype,
                        "normalized_card_subtype": normalize_card_subtype_for_brand(
                            brand,
                            clean_subtype,
                            frontend_type,
                        ),
                        "processing_method": method,
                        "feedback_note": feedback_note,
                        "multiplier": multiplier,
                        "denom_min": denom_min,
                        "denom_max": denom_max,
                        "range_type": range_type_for_values(denom_min, denom_max),
                        "supplier_rate": supplier_rate,
                        "status": line_status,
                        "requirements": requirements,
                        "confidence": round(max(0.1, min(confidence, 1.0)), 2),
                        "received_at": now.isoformat(sep=" "),
                        "expires_at": expires_at.isoformat(sep=" "),
                        "created_by": created_by.strip(),
                    }
                )

    return rows


def parse_title_context(line: str) -> dict[str, Any]:
    cleaned = _clean_title_line(line)
    same_price_image_and_code = _has_image_and_code_same_price(cleaned) or bool(
        _card_image_secret_pair(cleaned)
    )
    brand = standardize_brand(cleaned)
    country, currency = standardize_country_currency(cleaned)
    country_variants = eur_country_variants(cleaned) if has_generic_eur(cleaned) else []
    frontend_type = "" if same_price_image_and_code else standardize_frontend_type(cleaned)
    subtype = "" if same_price_image_and_code else standardize_subtype(cleaned, frontend_type)
    method = _explicit_processing_method(cleaned)
    feedback_note = extract_feedback_note(line)
    multiplier = extract_multiplier(cleaned)
    if multiplier is None:
        multiplier, _ = extract_card_count_multiplier(cleaned, None)
    requirements = "" if country_variants else _country_hint_requirement(cleaned, country)
    if "批量问" in cleaned:
        requirements = _append_text(requirements, "批量问")
    elif brand == "PSN" and re.search(r"批量.*问", cleaned):
        requirements = _append_text(requirements, "批量提前问")
    if brand == "Amazon" and "连卡大卡问" in cleaned:
        requirements = _append_text(requirements, "连卡大卡问")
    if brand == "Paysafecard":
        if "其他国家问" in cleaned:
            requirements = _append_text(requirements, "其他国家问")
        if "发前问" in cleaned:
            requirements = _append_text(requirements, "发前问")

    if brand and not same_price_image_and_code and not subtype:
        same_price_image_and_code = True
        frontend_type = ""
        subtype = ""

    context = {
        "brand": brand,
        "country": country,
        "currency": currency,
        "frontend_type": frontend_type,
        "subtype": subtype,
        "processing_method": method,
        "feedback_note": feedback_note,
        "multiplier": multiplier,
        "requirements": requirements,
        "country_variants": country_variants,
        "quote_same_type": "image_and_code_same_price" if same_price_image_and_code else "",
    }
    return {key: value for key, value in context.items() if value not in (None, "", [])}


def classify_numbers_in_line(line: str) -> dict[str, Any]:
    """Classify numeric roles before any value is allowed to become a quote rate."""
    normalized = _normalize_input_line(line)
    ranges: list[dict[str, Any]] = []
    for match in RANGE_RE.finditer(normalized):
        if _looks_like_feedback_time(normalized, *match.span()):
            continue
        first = _parse_denom_number(match.group("min"))
        second = _parse_denom_number(match.group("max"))
        ranges.append(
            {
                "min": min(first, second),
                "max": max(first, second),
                "span": match.span(),
            }
        )

    open_ranges = [
        {"min": _above_minimum(match), "max": None, "span": match.span()}
        for match in ABOVE_RE.finditer(normalized)
    ]
    multipliers = [
        {
            "value": float(match.group("value")),
            "span": match.span("value"),
        }
        for match in MULTIPLIER_NUMBER_RE.finditer(normalized)
    ]
    unit_spans = [match.span() for match in UNIT_NUMBER_RE.finditer(normalized)]

    fixed_match = FIXED_DENOM_PRICE_RE.search(normalized)
    fixed_denom = None
    fixed_denom_span = None
    if fixed_match:
        fixed_denom = float(fixed_match.group("denom"))
        fixed_denom_span = fixed_match.span("denom")

    role_spans = [item["span"] for item in ranges]
    role_spans.extend(item["span"] for item in open_ranges)
    role_spans.extend(item["span"] for item in multipliers)
    role_spans.extend(unit_spans)
    if fixed_denom_span:
        role_spans.append(fixed_denom_span)

    candidates: list[dict[str, Any]] = []

    def add_candidate(value: str, span: tuple[int, int], kind: str) -> None:
        if _span_inside_any(span, role_spans):
            return
        if _looks_like_multiplier(normalized, *span) or _is_duration_number(normalized, *span):
            return
        if any(item["span"] == span for item in candidates):
            return
        candidates.append({"value": Decimal(value), "span": span, "kind": kind})

    if fixed_match:
        add_candidate(fixed_match.group("rate"), fixed_match.span("rate"), "fixed_denom_price")

    for match in BRACKET_RATE_RE.finditer(normalized):
        add_candidate(match.group("rate"), match.span("rate"), "bracket_price")

    for match in PRICE_RE.finditer(normalized):
        operator_text = normalized[match.start() : match.start("rate")]
        kind = "equals_price" if "=" in operator_text else "colon_price"
        add_candidate(match.group("rate"), match.span("rate"), kind)

    market_rate_match = _market_rate_range_match(normalized)
    if market_rate_match:
        add_candidate(
            market_rate_match.group("rate"),
            market_rate_match.span("rate"),
            "market_range_price",
        )

    for item in ranges:
        suffix = normalized[item["span"][1] :]
        match = re.match(r"\s*[:：]?\s*(?P<rate>\d+(?:\.\d+)?)(?!\s*倍)", suffix)
        if match:
            start = item["span"][1] + match.start("rate")
            end = item["span"][1] + match.end("rate")
            add_candidate(match.group("rate"), (start, end), "range_price")

    country, currency = standardize_country_currency(normalized)
    if (country and currency) or _combined_country_variants(normalized):
        match = re.search(r"(?P<rate>\d+(?:\.\d+)?)\s*$", normalized)
        if match:
            add_candidate(match.group("rate"), match.span("rate"), "market_price")

    return {
        "ranges": ranges,
        "range_min": ranges[0]["min"] if ranges else None,
        "range_max": ranges[0]["max"] if ranges else None,
        "open_ranges": open_ranges,
        "open_range_min": open_ranges[0]["min"] if open_ranges else None,
        "fixed_denom": fixed_denom,
        "fixed_denom_span": fixed_denom_span,
        "multipliers": multipliers,
        "multiplier": multipliers[0]["value"] if multipliers else None,
        "supplier_rate_candidates": candidates,
    }


def extract_multiplier(line: str) -> float | None:
    patterns = [
        r"[\[【(（]\s*(1000|100|50|10|5|1)\s*(?:的\s*)?倍(?:数)?\s*[\]】)）]?",
        r"(?<![\d.])(1000|100|50|10|5|1)\s*(?:的\s*)?倍(?:数)?",
        r"[xX]\s*(1000|100|50|10|5|1)(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return float(match.group(1))
    return None


def extract_card_count_multiplier(line: str, explicit_multiplier: float | None = None) -> tuple[float | None, str]:
    compact = re.sub(r"\s+", "", line)
    has_loose = "散卡" in compact
    has_whole = "整卡" in compact
    suggested = 50.0 if has_whole else 5.0 if has_loose else None
    if explicit_multiplier is None or suggested is None:
        return suggested, ""
    if has_whole and explicit_multiplier != 50:
        return explicit_multiplier, f"整卡默认50倍，但原文明确为{int(explicit_multiplier)}倍数，已按原文{int(explicit_multiplier)}倍处理"
    if has_loose and explicit_multiplier != 5:
        return explicit_multiplier, f"散卡默认5倍，但原文明确为{int(explicit_multiplier)}倍数，已按原文{int(explicit_multiplier)}倍处理"
    return explicit_multiplier, ""


def extract_denom_options(
    line: str,
    rate_span: tuple[int, int] | None = None,
) -> list[tuple[float, float | None, tuple[int, int], str]]:
    bracket_rate_match = BRACKET_RATE_RE.search(line)
    if bracket_rate_match and rate_span:
        for range_match in RANGE_RE.finditer(line, rate_span[1]):
            if _looks_like_feedback_time(line, *range_match.span()):
                continue
            first = _parse_denom_number(range_match.group("min"))
            second = _parse_denom_number(range_match.group("max"))
            return [(min(first, second), max(first, second), range_match.span(), "")]

    market_rate_match = _market_rate_range_match(line)
    if market_rate_match:
        first = _parse_denom_number(market_rate_match.group("min"))
        second = _parse_denom_number(market_rate_match.group("max"))
        return [(min(first, second), max(first, second), market_rate_match.span("range"), "")]

    price_operator_span = _price_operator_span(line)
    search_end = price_operator_span[0] if price_operator_span else (rate_span[0] if rate_span else len(line))
    prefix = line[:search_end]
    above = ABOVE_RE.search(prefix)
    if above:
        return [(_above_minimum(above), None, above.span(), "")]

    range_match = None
    for match in RANGE_RE.finditer(prefix):
        if _looks_like_feedback_time(prefix, *match.span()):
            continue
        range_match = match
    if range_match:
        first = _parse_denom_number(range_match.group("min"))
        second = _parse_denom_number(range_match.group("max"))
        return [(min(first, second), max(first, second), range_match.span(), "")]

    face = FACE_VALUE_RE.search(prefix)
    if face:
        values = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", face.group(0))]
        return [(value, value, face.span(), "单张固定面值") for value in values]

    fixed_matches = [
        match
        for match in FIXED_DENOM_RE.finditer(prefix)
        if not _looks_like_multiplier(prefix, *match.span())
        and not _is_duration_number(prefix, *match.span())
    ]
    if not fixed_matches:
        return []
    fixed = fixed_matches[-1]
    values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", fixed.group("values"))]
    return [(value, value, fixed.span(), "单张固定面值") for value in values]


def extract_denom_range(line: str) -> tuple[float | None, float | None, tuple[int, int] | None, str]:
    face = FACE_VALUE_RE.search(line)
    if face:
        values = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", face.group(0))]
        return min(values), max(values), face.span(), face.group(0)

    above = ABOVE_RE.search(line)
    if above:
        return _above_minimum(above), None, above.span(), ""

    match = RANGE_RE.search(line)
    if match:
        first = _parse_denom_number(match.group("min"))
        second = _parse_denom_number(match.group("max"))
        return min(first, second), max(first, second), match.span(), ""

    return None, None, None, ""


def _above_minimum(match: re.Match[str]) -> float:
    return float(match.group("leading") or match.group("trailing"))


def _parse_denom_number(value: str) -> float:
    cleaned = re.sub(r"\s+", "", value)
    multiplier = 10000 if cleaned[-1:].lower() == "w" or cleaned.endswith("万") else 1
    if multiplier != 1:
        cleaned = cleaned[:-1]
    return float(cleaned) * multiplier


def extract_supplier_rate(
    line: str,
    ignored_spans: list[tuple[int, int]],
    multiplier: float | None = None,
) -> tuple[Decimal | None, tuple[int, int] | None]:
    if PAUSED_PRICE_RE.search(line):
        return None, None
    classification = classify_numbers_in_line(line)
    for candidate in classification["supplier_rate_candidates"]:
        if not _span_inside_any(candidate["span"], ignored_spans):
            return candidate["value"], candidate["span"]
    return None, None


def extract_subtype_candidates(
    line: str,
    range_span: tuple[int, int] | None,
    rate_span: tuple[int, int] | None,
) -> tuple[list[str], str]:
    expression = ""
    if range_span:
        start = range_span[1]
        end = rate_span[0] if rate_span else len(line)
        expression = line[start:end]
        expression = re.split(r"=", expression, maxsplit=1)[0]
        expression = re.sub(r"\[[^\]]+\]", "", expression)
        expression = re.sub(r"[：:，,;；\s]", "", expression)
        expression = expression.strip()

    if expression and "面值" not in expression:
        compound = _compound_card_image_subtypes(expression)
        if compound:
            return compound, ""
        subtype_pair = _card_image_secret_pair(expression)
        if subtype_pair:
            return subtype_pair, ""
        parts = [part for part in re.split(r"[/／、和&]+", expression) if part]
        mapped = [standardize_subtype(part) or part for part in parts]
        mapped = [part for part in mapped if part and part != "普通物理卡"]
        if mapped:
            return list(dict.fromkeys(mapped)), ""

    scanned = _scan_subtypes(line)
    if scanned:
        return scanned, ""
    if _has_card_count_word(line):
        return ["卡图"], "散卡/整卡仅用于倍数，细分默认卡图"
    return [], "未识别细分，使用上下文或待确认"


def extract_requirements(line: str, status: str) -> str:
    keywords = ["发前问", "提前问", "锁卡", "拒付", "不结算", "限", "备注", "慢反馈"]
    found = [keyword for keyword in keywords if keyword in line]
    if status != "active" and not found:
        return line
    return "；".join(dict.fromkeys(found))


def extract_market_rate_requirements(line: str) -> str:
    match = _market_rate_range_match(line)
    if not match:
        return ""
    inside = _clean_requirement_fragment(match.group("inside"))
    trailing = _clean_requirement_fragment(match.group("trailing"))
    return _append_text(inside, trailing)


def extract_bracket_requirements(line: str) -> str:
    requirements = []
    for match in re.finditer(r"[\[【](?P<text>[^\]】]+)[\]】]", line):
        value = _clean_requirement_fragment(match.group("text"))
        if not value:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            continue
        if re.search(r"\d+\s*倍", value):
            continue
        if standardize_subtype(value) or _explicit_processing_method(value):
            continue
        country, currency = standardize_country_currency(value)
        if country or currency:
            continue
        requirements.append(value)
    return "；".join(dict.fromkeys(requirements))


def method_label(value: str | None) -> str:
    return METHOD_LABELS.get(value or "", value or "")


def status_label(value: str | None) -> str:
    if value == "no_available_quote":
        return "无可用报价"
    return STATUS_LABELS.get(value or "", value or "")


def subtype_options() -> list[str]:
    return SUBTYPE_OPTIONS


def normalized_subtype_options() -> list[str]:
    return NORMALIZED_CARD_SUBTYPE_OPTIONS


def range_type_for_values(denom_min: float | None, denom_max: float | None) -> str:
    if denom_min is None and denom_max is None:
        return "unlimited"
    if denom_min is not None and denom_max is None:
        return "open"
    if denom_min is not None and denom_max is not None and denom_min == denom_max:
        return "fixed"
    return "bounded"


def _empty_context() -> dict[str, Any]:
    return {
        "brand": "",
        "country": "",
        "currency": "",
        "frontend_type": "",
        "subtype": "",
        "processing_method": "",
        "feedback_note": "",
        "multiplier": None,
        "denom_min": None,
        "denom_max": None,
        "range_type": "unlimited",
        "requirements": "",
        "country_variants": [],
        "quote_same_type": "",
    }


def _default_context(
    brand: str = "",
    market: str = "",
    processing_method: str = "",
    multiplier: float | None = None,
    subtype: str = "",
) -> dict[str, Any]:
    country, currency = split_market_value(market)
    clean_subtype = standardize_subtype(subtype) or (
        subtype.strip() if subtype.strip() in NORMALIZED_CARD_SUBTYPE_OPTIONS else ""
    )
    return {
        "brand": normalize_brand(brand) or brand.strip(),
        "country": country,
        "currency": currency,
        "processing_method": processing_method if processing_method in METHOD_LABELS else "",
        "multiplier": multiplier,
        "subtype": clean_subtype,
    }


def _fallback_row(
    supplier_group: str,
    line: str,
    default_expire_hours: float,
    created_by: str,
    line_no: int,
) -> dict[str, Any]:
    now = datetime.now().replace(microsecond=0)
    expires_at = _expires_at(line, now, default_expire_hours)
    return {
        "supplier_group": supplier_group.strip(),
        "source_text": line,
        "source_line": line,
        "line_no": line_no,
        "parse_note": "未能按报价行格式解析",
        "brand": "",
        "country": "",
        "currency": "",
        "frontend_type": "physical",
        "subtype": "待确认",
        "raw_card_subtype": "待确认",
        "normalized_card_subtype": "待确认",
        "processing_method": "fast_card",
        "multiplier": None,
        "denom_min": None,
        "denom_max": None,
        "supplier_rate": None,
        "status": standardize_status(line),
        "requirements": extract_requirements(line, standardize_status(line)),
        "confidence": 0.2,
        "received_at": now.isoformat(sep=" "),
        "expires_at": expires_at.isoformat(sep=" "),
        "created_by": created_by.strip(),
    }


def _normalize_input_line(line: str) -> str:
    cleaned = DECORATION_RE.sub("", line or "")
    cleaned = cleaned.translate(str.maketrans({"：": ":", "～": "~", "－": "-"}))
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _extract_block_requirement(line: str) -> str:
    match = BLOCK_REQUIREMENT_RE.match(line)
    return _clean_requirement_fragment(match.group("text")) if match else ""


def _extract_question_requirement(line: str) -> str:
    match = QUESTION_NOTE_RE.match(line)
    return _clean_requirement_fragment(match.group("text")) if match else ""


def _is_special_unbounded_quote(
    line: str,
    context: dict[str, Any],
    default_context: dict[str, Any],
) -> bool:
    brand = standardize_brand(line) or context.get("brand") or default_context.get("brand") or ""
    country, currency = standardize_country_currency(line)
    recognized_brand_quote = bool(brand and country and currency)
    supports_unbounded = (
        recognized_brand_quote
        or context.get("quote_same_type") == "image_and_code_same_price"
    )
    if not supports_unbounded or not _has_explicit_numeric_price(line):
        return False
    price_match = PRICE_RE.search(line) or BRACKET_RATE_RE.search(line)
    return not extract_denom_options(line, price_match.span("rate") if price_match else None)


def _has_explicit_numeric_price(line: str) -> bool:
    return any(
        candidate["kind"] in {"equals_price", "colon_price", "bracket_price"}
        for candidate in classify_numbers_in_line(line)["supplier_rate_candidates"]
    )


def _parse_pending_rate_line(line: str) -> dict[str, Any] | None:
    match = PENDING_SAME_RATE_RE.search(line)
    if not match or RANGE_RE.search(line):
        return None
    country, currency = standardize_country_currency(line)
    if not country or not currency:
        return None
    return {
        "country": country,
        "currency": currency,
        "supplier_rate": Decimal(match.group("rate")),
        "quote_type": "图/密同价",
    }


def _parse_pending_denom_line(line: str) -> dict[str, Any] | None:
    if not PENDING_DENOM_PREFIX_RE.match(line):
        return None
    range_match = RANGE_RE.search(line)
    if not range_match:
        return None
    first = _parse_denom_number(range_match.group("min"))
    second = _parse_denom_number(range_match.group("max"))
    return {
        "denom_min": min(first, second),
        "denom_max": max(first, second),
        "multiplier": extract_multiplier(line),
    }


def _pending_quote_synthetic_line(
    pending_quote: dict[str, Any],
    pending_denom: dict[str, Any],
) -> str:
    multiplier_text = ""
    if pending_denom.get("multiplier") is not None:
        multiplier_text = f" {format(pending_denom['multiplier'], 'g')}倍数"
    return (
        f"{pending_quote['country']} {pending_quote['currency']} "
        f"{format(pending_denom['denom_min'], 'g')}-{format(pending_denom['denom_max'], 'g')}"
        f"图/密={decimal_text(pending_quote['supplier_rate'])}{multiplier_text}"
    )


def _has_price(line: str) -> bool:
    if PAUSED_PRICE_RE.search(line):
        return bool(extract_denom_options(line))
    candidates = classify_numbers_in_line(line)["supplier_rate_candidates"]
    for candidate in candidates:
        if candidate["kind"] in {"fixed_denom_price", "range_price", "market_range_price", "market_price"}:
            return True
        if extract_denom_options(line, candidate["span"]):
            return True
    return False


def _is_separator_line(line: str) -> bool:
    return bool(SEPARATOR_RE.fullmatch(line.strip()))


def _is_comment_line(line: str) -> bool:
    return bool(COMMENT_PREFIX_RE.match(line))


def _strip_comment_prefix(line: str) -> str:
    return COMMENT_PREFIX_RE.sub("", line, count=1).strip()


def _is_plain_requirement_line(line: str) -> bool:
    markers = ("备注", "要求", "漏卡", "提醒", "没回", "纠纷", "不接受", "不要", "赎回", "多发卡")
    return any(marker in line for marker in markers)


def _combined_country_variants(line: str) -> list[tuple[str, str]]:
    if "比爱奥" in line:
        return [("Belgium", "EUR"), ("Ireland", "EUR"), ("Austria", "EUR")]
    if re.search(r"比\s*/\s*意\s*/\s*奥\s*/?", line):
        return [("Belgium", "EUR"), ("Italy", "EUR"), ("Austria", "EUR")]
    if re.search(r"欧盟\s*/\s*英国", line):
        return [("EU", "EUR"), ("UK", "GBP")]
    if re.search(r"瑞典\s*/\s*挪威", line):
        return [("Sweden", "SEK"), ("Norway", "NOK")]
    return []


def _split_multi_market_quote_segments(line: str) -> list[str]:
    matches = list(MULTI_MARKET_SEGMENT_RE.finditer(line))
    if len(matches) < 2:
        return []
    segments = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        suffix = line[match.end() : next_start].strip()
        label = f"{match.group('label')}{match.group('brand') or ''}".strip()
        label = label.replace("瑞 士", "瑞士").replace("日 本", "日本")
        segment = f"{label}={match.group('rate')}"
        if suffix:
            segment = f"{segment} {suffix}"
        segments.append(segment)
    return segments


def _explicit_dual_type_segments(line: str) -> list[str]:
    match = EXPLICIT_DUAL_TYPE_RATE_RE.search(line)
    if not match:
        return []
    market = match.group("market")
    return [
        f"{market} 卡图={match.group('physical_rate')}",
        f"{market} 代码={match.group('code_rate')}",
    ]


def _amazon_dual_type_segments(
    line: str,
    context: dict[str, Any],
    default_context: dict[str, Any],
) -> list[str]:
    brand = standardize_brand(line) or context.get("brand") or default_context.get("brand") or ""
    if brand != "Amazon":
        return []

    physical_patterns = [
        re.compile(r"=+\s*(?P<rate>\d+(?:\.\d+)?)\s*(?:卡图|图)(?!\s*[/／]?\s*密)"),
        re.compile(r"(?:卡图|(?<![/／图])图)\s*[:=]?\s*(?P<rate>\d+(?:\.\d+)?)"),
    ]
    code_patterns = [
        re.compile(r"(?:代码|卡密|(?<!图)密)\s*[:=]?\s*(?P<rate>\d+(?:\.\d+)?)"),
        re.compile(r"=+\s*(?P<rate>\d+(?:\.\d+)?)\s*(?:代码|卡密|密)"),
    ]
    physical_match = next((pattern.search(line) for pattern in physical_patterns if pattern.search(line)), None)
    code_match = next((pattern.search(line) for pattern in code_patterns if pattern.search(line)), None)
    if not physical_match or not code_match:
        return []

    range_match = RANGE_RE.search(line)
    if not range_match:
        return []
    minimum = _parse_denom_number(range_match.group("min"))
    maximum = _parse_denom_number(range_match.group("max"))
    range_text = f"{format(min(minimum, maximum), 'g')}-{format(max(minimum, maximum), 'g')}"
    country, currency = standardize_country_currency(line)
    market_text = f"{country} {currency}".strip()
    multiplier = extract_multiplier(line)
    multiplier_text = f" {format(multiplier, 'g')}倍数" if multiplier is not None else ""
    status_text = " 发前问" if standardize_status(line) == "ask_first" else ""
    prefix = f"Amazon {market_text} {range_text}".strip()
    return [
        f"{prefix} 卡图={physical_match.group('rate')}{multiplier_text}{status_text}",
        f"{prefix} 代码={code_match.group('rate')}{multiplier_text}{status_text}",
    ]


def _multi_range_rate_segments(line: str) -> list[dict[str, str]]:
    matches = list(MULTI_RANGE_RATE_PAIR_RE.finditer(line))
    if len(matches) < 2:
        return []
    prefix = line[: matches[0].start()].strip()
    shared_subtype = _shared_subtype_marker(line)
    multiplier = extract_multiplier(line)
    multiplier_text = f" {format(multiplier, 'g')}倍数" if multiplier is not None else ""
    status_text = " 发前问" if standardize_status(line) == "ask_first" else ""
    variant_match = re.search(r"\b(?P<variant>Macy(?:/\d+)+)(?!\w)", line, re.IGNORECASE)
    requirements = f"品牌变体：{variant_match.group('variant')}" if variant_match else ""
    segments = []
    for match in matches:
        type_text = f" {shared_subtype}" if shared_subtype else ""
        segments.append(
            {
                "line": (
                    f"{prefix} {match.group('denom')}{type_text}={match.group('rate')}"
                    f"{multiplier_text}{status_text}"
                ).strip(),
                "requirements": requirements,
            }
        )
    return segments


def _shared_subtype_marker(line: str) -> str:
    if _card_image_secret_pair(line):
        return "图/密"
    compact = re.sub(r"\s+", "", line)
    lower = line.lower()
    if "电子" in compact or re.search(r"(?<![a-z0-9])e-?card(?![a-z0-9])", lower):
        return "电子卡"
    if any(token in compact for token in ["代码", "卡密", "纯代码"]):
        return "代码"
    if "横白" in compact:
        return "横白"
    if "竖卡" in compact:
        return "竖卡"
    if any(token in compact for token in ["卡图", "横卡", "白卡", "散卡", "整卡"]):
        return "卡图"
    return ""


def _loose_quote_segments(
    line: str,
    context: dict[str, Any],
    default_context: dict[str, Any],
) -> list[str]:
    number_roles = classify_numbers_in_line(line)
    if (
        "=" in line
        or BRACKET_RATE_RE.search(line)
        or _market_rate_range_match(line)
        or PENDING_SAME_RATE_RE.search(line)
        or "倍数" in line and not number_roles["ranges"] and number_roles["fixed_denom"] is None
    ):
        return []

    brand = standardize_brand(line) or context.get("brand") or default_context.get("brand") or ""
    if brand in {"Roblox", "PSN"}:
        return []
    line_country, line_currency = standardize_country_currency(line)
    country = line_country or context.get("country") or default_context.get("country") or ""
    currency = line_currency or context.get("currency") or default_context.get("currency") or ""
    combined_countries = _combined_country_variants(line)
    subtype_marker = _loose_original_subtype_marker(line)
    multiplier = extract_multiplier(line)
    multiplier_text = f" {format(multiplier, 'g')}倍数" if multiplier is not None else ""
    status_text = " 发前问" if standardize_status(line) == "ask_first" else ""

    if number_roles["ranges"]:
        range_item = number_roles["ranges"][0]
        rate_candidate = next(
            (
                candidate
                for candidate in number_roles["supplier_rate_candidates"]
                if candidate["kind"] == "range_price"
            ),
            None,
        )
        if not rate_candidate:
            return []
        range_text = f"{format(range_item['min'], 'g')}-{format(range_item['max'], 'g')}"
        return [
            _loose_synthetic_line(
                brand,
                country,
                currency,
                range_text,
                subtype_marker,
                decimal_text(rate_candidate["value"]),
                multiplier_text,
                status_text,
            )
        ]

    fixed_rate_candidate = next(
        (
            candidate
            for candidate in number_roles["supplier_rate_candidates"]
            if candidate["kind"] == "fixed_denom_price"
        ),
        None,
    )
    if number_roles["fixed_denom"] is not None and fixed_rate_candidate:
        return [
            _loose_synthetic_line(
                brand,
                country,
                currency,
                format(number_roles["fixed_denom"], "g"),
                subtype_marker,
                decimal_text(fixed_rate_candidate["value"]),
                multiplier_text,
                status_text,
            )
        ]

    if not combined_countries and not (line_country and line_currency):
        return []
    rate_candidate = next(
        (
            candidate
            for candidate in number_roles["supplier_rate_candidates"]
            if candidate["kind"] == "market_price"
        ),
        None,
    )
    if not rate_candidate:
        return []
    market_text = "比/意/奥/" if combined_countries else ""
    return [
        _loose_synthetic_line(
            brand,
            country,
            currency,
            "",
            subtype_marker,
            decimal_text(rate_candidate["value"]),
            multiplier_text,
            status_text,
            market_text=market_text,
        )
    ]


def _loose_synthetic_line(
    brand: str,
    country: str,
    currency: str,
    denom_text: str,
    subtype: str,
    rate: str,
    multiplier_text: str,
    status_text: str,
    market_text: str = "",
) -> str:
    market = market_text or f"{country} {currency}".strip()
    parts = [brand, market, denom_text, subtype]
    prefix = " ".join(part for part in parts if part)
    return f"{prefix}={rate}{multiplier_text}{status_text}".strip()


def _loose_original_subtype_marker(line: str) -> str:
    compact = re.sub(r"\s+", "", line)
    lower = line.lower()
    if _card_image_secret_pair(line):
        return "图/密"
    if "电子" in compact or re.search(r"(?<![a-z0-9])e-?card(?![a-z0-9])", lower):
        return "电子卡"
    if any(token in compact for token in ["代码", "卡密", "纯代码"]):
        return "代码"
    if "横白" in compact:
        return "横白"
    if "竖卡" in compact:
        return "竖卡"
    if "整卡" in compact:
        return "整卡"
    if "散卡" in compact:
        return "散卡"
    if any(token in compact for token in ["卡图", "横卡", "白卡", "图"]):
        return "卡图"
    return ""


def _context_denom_from_line(line: str) -> tuple[float, float | None] | None:
    number_roles = classify_numbers_in_line(line)
    if number_roles["open_ranges"]:
        return number_roles["open_ranges"][0]["min"], None
    return None


def _roblox_matrix_segments(
    line: str,
    context: dict[str, Any],
    default_context: dict[str, Any],
) -> tuple[list[str], str]:
    brand = standardize_brand(line) or context.get("brand") or default_context.get("brand") or ""
    if brand != "Roblox" or RANGE_RE.search(line):
        return [], ""
    matches = list(ROBLOX_MATRIX_RE.finditer(line))
    if not matches:
        return [], ""
    segments = []
    for match in matches:
        label = match.group("label")
        currency = match.group("currency") or ""
        market_text = f"{label} {currency}".strip()
        segments.append(f"{market_text}={match.group('rate')}")
    trailing_note = _clean_requirement_fragment(line[matches[-1].end() :])
    return segments, trailing_note


def _psn_matrix_segments(
    line: str,
    context: dict[str, Any],
    default_context: dict[str, Any],
) -> list[dict[str, Any]]:
    brand = standardize_brand(line) or context.get("brand") or default_context.get("brand") or ""
    if brand != "PSN":
        return []

    pure_digital = PSN_PURE_DIGITAL_RE.search(line)
    if pure_digital:
        return [
            {
                "line": f"代码={pure_digital.group('rate')}",
                "market": ("", ""),
                "requirements": "纯数字PSN",
            }
        ]

    matches = list(PSN_MATRIX_RE.finditer(line))
    if not matches:
        return []

    segments: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        suffix = line[match.end() : next_start]
        market_text = f"{match.group('label')} {match.group('currency') or ''}".strip()
        country, currency = standardize_country_currency(market_text)
        if not country or not currency:
            continue

        range_match = RANGE_RE.search(suffix)
        range_text = ""
        if range_match:
            minimum = _parse_denom_number(range_match.group("min"))
            maximum = _parse_denom_number(range_match.group("max"))
            range_text = f"{format(min(minimum, maximum), 'g')}-{format(max(minimum, maximum), 'g')}"

        segment_requirements = ""
        question_above = re.search(r"\d+(?:\.\d+)?\s*(?:以上|\+)\s*问", suffix)
        if question_above:
            segment_requirements = re.sub(r"\s+", "", question_above.group(0))

        is_ask_first = bool(re.search(r"[（(]\s*问\s*[）)]", suffix))
        market_prefix = f"{country} {currency}"
        main_line = f"{market_prefix} {range_text}={match.group('rate')}".strip()
        if is_ask_first:
            main_line = f"{main_line} 发前问"
        segments.append(
            {
                "line": main_line,
                "market": (country, currency),
                "requirements": segment_requirements,
            }
        )

        second_tier = PSN_SECOND_TIER_RE.search(suffix)
        if second_tier:
            segments.append(
                {
                    "line": (
                        f"{market_prefix} {second_tier.group('min')}以上="
                        f"{second_tier.group('rate')}"
                    ),
                    "market": (country, currency),
                    "requirements": "",
                }
            )

    return segments


def _starts_psn_eur_country_list(line: str) -> bool:
    return line.lstrip().startswith(("（", "(")) and bool(eur_country_variants(line))


def _expand_psn_eur_rows(
    rows: list[dict[str, Any]],
    row_indexes: list[int],
    country_variants: list[tuple[str, str]],
    country_source_lines: list[str],
    block_row_indexes: list[int],
) -> list[int]:
    if not row_indexes:
        return block_row_indexes
    start = min(row_indexes)
    end = max(row_indexes) + 1
    base_rows = [dict(rows[index]) for index in row_indexes]
    country_source = "\n".join(country_source_lines)
    expanded_rows = []
    for country, currency in country_variants:
        for base_row in base_rows:
            row = dict(base_row)
            row["country"] = country
            row["currency"] = currency
            row["source_text"] = f"{base_row['source_line']}\n{country_source}"
            row["source_line"] = row["source_text"]
            row["parse_note"] = _append_text(
                base_row.get("parse_note"), "由 EUR 后续具体国家列表拆分"
            )
            expanded_rows.append(row)

    rows[start:end] = expanded_rows
    shift = len(expanded_rows) - (end - start)
    updated_indexes = []
    for index in block_row_indexes:
        if index < start:
            updated_indexes.append(index)
        elif index >= end:
            updated_indexes.append(index + shift)
    updated_indexes.extend(range(start, start + len(expanded_rows)))
    return list(dict.fromkeys(updated_indexes))


def _extract_bracket_quote_trailing_requirement(
    line: str,
    range_span: tuple[int, int] | None,
) -> str:
    if not range_span or not BRACKET_RATE_RE.search(line):
        return ""
    trailing = line[range_span[1] :]
    trailing = re.sub(
        r"[（(]?\s*(?:1000|100|50|10|5|1)\s*倍(?:数)?\s*[）)]?",
        "",
        trailing,
    )
    return _clean_requirement_fragment(trailing)


def _extract_unbounded_bracket_trailing_requirement(
    line: str,
    range_span: tuple[int, int] | None,
) -> str:
    if range_span:
        return ""
    rate_match = BRACKET_RATE_RE.search(line)
    if not rate_match:
        return ""
    return _clean_requirement_fragment(line[rate_match.end() :])


def _clean_title_line(line: str) -> str:
    cleaned = re.sub(r"[=_\-—–]+", " ", line)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_feedback_note(line: str) -> str:
    notes = []
    method_note = _method_feedback_note(line)
    if method_note:
        notes.append(method_note)
    for match in FEEDBACK_TIME_RE.finditer(line):
        time_note = match.group(0).strip(" -~—–")
        if not _feedback_time_already_covered(time_note, method_note):
            notes.append(time_note)
    if "使用时间" in line and "使用时间" not in notes:
        notes.append("使用时间")
    return "；".join(dict.fromkeys(notes))


def _method_feedback_note(text: str) -> str:
    if "极速快刷" in text:
        return METHOD_FEEDBACK_NOTES["quick_fast_process"]
    if "快刷网单" in text:
        return METHOD_FEEDBACK_NOTES["web_fast_process"]
    if "慢刷" in text or "慢网" in text:
        return METHOD_FEEDBACK_NOTES["slow_process"]
    if "快刷" in text or "快网" in text:
        return METHOD_FEEDBACK_NOTES["fast_process"]
    if "快卡" in text or "快加" in text:
        return METHOD_FEEDBACK_NOTES["fast_card"]
    return ""


def _feedback_time_already_covered(time_note: str, method_note: str) -> bool:
    if not method_note:
        return False
    normalized_time = re.sub(r"\s+", "", time_note).lower()
    normalized_method = re.sub(r"\s+", "", method_note).lower()
    normalized_time = normalized_time.replace("mins", "分钟").replace("min", "分钟").replace("分", "分钟")
    return any(token in normalized_time and token in normalized_method for token in ["1-5", "10-15", "5-20", "1-2"])


def _explicit_processing_method(text: str) -> str:
    if any(token in text for token in ["快卡", "快加", "快刷", "快网", "慢刷", "慢网"]):
        return standardize_processing_method(text)
    return ""


def _expires_at(line: str, now: datetime, default_expire_hours: float) -> datetime:
    expire_minutes = 30 if ("半小时" in line or re.search(r"30\s*分钟", line)) else None
    return now + (timedelta(minutes=expire_minutes) if expire_minutes else timedelta(hours=default_expire_hours))


def _frontend_type_for_subtype(subtype: str) -> str:
    if subtype in {"代码/卡密", "代码", "电子图", "电子卡"}:
        return "code"
    if subtype in {"横白", "横卡", "竖卡", "白卡", "散卡", "整卡", "整卡/散卡", "卡图", "普通物理卡"}:
        return "physical"
    return ""


def _scan_subtypes(line: str) -> list[str]:
    compound = _compound_card_image_subtypes(line)
    if compound:
        return compound
    pair = _card_image_secret_pair(line)
    if pair:
        return pair
    if "电子" in line or re.search(r"(?<![a-z0-9])e-?card(?![a-z0-9])", line, re.IGNORECASE):
        return ["电子卡"]
    tokens = [
        "普通物理卡",
        "电子卡",
        "电子图",
        "电子",
        "e-card",
        "ecard",
        "代码/卡密",
        "纯代码",
        "散卡",
        "横卡",
        "竖卡",
        "白卡",
        "卡图",
        "图卡",
        "卡密",
        "密卡",
        "代码",
        "图",
        "密",
    ]
    found = []
    for token in sorted(tokens, key=len, reverse=True):
        if token in line:
            subtype = standardize_subtype(token)
            if subtype and subtype not in found:
                found.append(subtype)
    return found


def _compound_card_image_subtypes(text: str) -> list[str]:
    compact = re.sub(r"[\s\[\]【】()（）]+", "", text)
    patterns: list[tuple[str, list[str]]] = [
        ("横白竖卡图", ["横卡", "白卡", "竖卡"]),
        ("横竖白卡图", ["横卡", "竖卡", "白卡"]),
        ("横白卡图", ["横卡", "白卡"]),
        ("横竖卡图", ["横卡", "竖卡"]),
        ("白竖卡图", ["白卡", "竖卡"]),
        ("横卡图", ["横卡"]),
        ("白卡图", ["白卡"]),
        ("竖卡图", ["竖卡"]),
    ]
    for pattern, subtypes in patterns:
        if pattern in compact:
            return subtypes
    if "卡图" in compact or "图卡" in compact:
        loose_patterns: list[tuple[str, list[str]]] = [
            ("横白竖", ["横卡", "白卡", "竖卡"]),
            ("横竖白", ["横卡", "竖卡", "白卡"]),
            ("横白", ["横卡", "白卡"]),
            ("横竖", ["横卡", "竖卡"]),
            ("白竖", ["白卡", "竖卡"]),
        ]
        for pattern, subtypes in loose_patterns:
            if pattern in compact:
                return subtypes
    standalone_patterns: list[tuple[str, list[str]]] = [
        ("横白竖", ["横卡", "白卡", "竖卡"]),
        ("横竖白", ["横卡", "竖卡", "白卡"]),
        ("横白", ["横卡", "白卡"]),
        ("横竖", ["横卡", "竖卡"]),
        ("白竖", ["白卡", "竖卡"]),
    ]
    for pattern, subtypes in standalone_patterns:
        if pattern in compact:
            return subtypes
    return []


def _has_card_count_word(text: str) -> bool:
    return "散卡" in text or "整卡" in text


def _score_confidence(
    brand: str,
    country: str,
    currency: str,
    frontend_type: str,
    subtype: str,
    denom_min: float | None,
    supplier_rate: Decimal | None,
    context: dict[str, Any],
    line_brand: str,
    line_country: str,
    line_currency: str,
    denom_optional: bool = False,
) -> tuple[float, list[str]]:
    confidence = 1.0
    notes = []
    if not brand:
        confidence -= 0.25
        notes.append("未识别品牌")
    elif not line_brand and context.get("brand"):
        confidence -= 0.02
    if not country or not currency:
        confidence -= 0.2
        notes.append("未识别国家/币种")
    elif not line_country and not line_currency and (context.get("country") or context.get("currency")):
        confidence -= 0.02
    if frontend_type not in {"physical", "code"}:
        confidence -= 0.15
        notes.append("未识别前台类型")
    if subtype == "待确认":
        confidence -= 0.25
        notes.append("细分待确认")
    if denom_min is None and not denom_optional:
        confidence -= 0.12
        notes.append("未识别面额范围")
    if supplier_rate is None:
        confidence -= 0.25
        notes.append("未识别报价")
    return confidence, notes


def _card_image_secret_pair(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    if _has_image_and_code_same_price(compact) or re.search(
        r"图[/／、和&]?密|图密|卡图[/／、和&]?卡密|卡图卡密|卡图[/／、和&]?代码",
        compact,
    ):
        return ["卡图", "代码/卡密"]
    return []


def _has_image_and_code_same_price(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return bool(re.search(r"密同(?:价)?", compact))


def _has_card_image_and_secret(subtypes: list[str]) -> bool:
    normalized = {standardize_subtype(item) or item for item in subtypes}
    return {"卡图", "代码/卡密"}.issubset(normalized)


def _apply_brand_subtype_rules(
    brand: str,
    line: str,
    subtypes: list[str],
) -> tuple[list[str], str]:
    if not subtypes:
        return subtypes, ""
    compact = re.sub(r"\s+", "", line)
    if brand == "Apple":
        if "横白" in compact and "竖" not in compact:
            return ["横白"], "Apple 横白保留为单一原始细分，不拆横卡/白卡"
        if "整卡" in compact and all(
            (standardize_subtype(item) or item) in {"卡图", "普通物理卡"}
            for item in subtypes
        ):
            return ["整卡"], "Apple 整卡保留原始细分，统一归类为卡图"
        return subtypes, ""

    if not brand:
        return subtypes, ""

    mapped: list[str] = []
    vertical_seen = False
    for subtype in subtypes:
        clean = standardize_subtype(subtype) or subtype
        if clean in {"横白", "横卡", "白卡", "竖卡", "散卡", "整卡", "普通物理卡"}:
            vertical_seen = vertical_seen or clean == "竖卡"
            clean = "卡图"
        if clean not in mapped:
            mapped.append(clean)
    note = "非 Apple 品牌出现竖卡，已归类为卡图" if vertical_seen else ""
    return mapped, note


def _inherit_note(context: dict[str, Any], line_brand: str, line_country: str, line_currency: str) -> str:
    inherited = []
    if context.get("brand") and not line_brand:
        inherited.append("品牌")
    if (context.get("country") or context.get("currency")) and not (line_country or line_currency):
        inherited.append("国家/币种")
    if context.get("requirements"):
        inherited.append("备注")
    return f"继承标题上下文：{','.join(inherited)}" if inherited else ""


def _country_hint_requirement(text: str, country: str) -> str:
    hints = []
    for country_name, _ in eur_country_variants(text):
        hints.append(country_name)
    if country == "EU" and hints:
        return "标题提到：" + "、".join(hints)
    return ""


def _append_text(base: Any, extra: Any) -> str:
    parts = [str(item).strip("；; ") for item in [base, extra] if item not in (None, "")]
    return "；".join(dict.fromkeys(part for part in parts if part))


def _span_inside_any(span: tuple[int, int], ranges: list[tuple[int, int] | None]) -> bool:
    start, end = span
    return any(item is not None and start >= item[0] and end <= item[1] for item in ranges)


def _price_operator_span(line: str) -> tuple[int, int] | None:
    match = re.search(r"(?<![<>])=+", line)
    if match:
        return match.span()
    match = re.search(r"[:：]", line)
    return match.span() if match else None


def _market_rate_range_match(line: str) -> re.Match[str] | None:
    if "=" in line:
        return None
    country, currency = standardize_country_currency(line)
    if not country or not currency:
        return None
    return MARKET_RATE_RANGE_RE.search(line)


def _clean_requirement_fragment(value: str | None) -> str:
    cleaned = (value or "").strip(" \t，,。.;；#~-—–")
    cleaned = re.sub(r"包\s*(\d+)\s*[hH]\b", lambda match: f"包{match.group(1)}H", cleaned)
    return cleaned.strip()


def _looks_like_feedback_time(line: str, start: int, end: int) -> bool:
    window = line[max(0, start - 4) : min(len(line), end + 10)]
    return bool(FEEDBACK_TIME_RE.search(window))


def _is_duration_number(line: str, start: int, end: int) -> bool:
    after = line[end : end + 8]
    return bool(re.search(r"\s*(?:min|mins|分钟|分|小时)", after, re.IGNORECASE))


def _looks_like_multiplier(line: str, start: int, end: int) -> bool:
    before = line[max(0, start - 1) : start]
    after = line[end : end + 3]
    return before.lower() == "x" or after.startswith("倍")
