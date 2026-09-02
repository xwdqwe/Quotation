from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil, floor
from typing import Any

from .parsing import method_label, status_label
from .standards import normalize_card_subtype_for_brand


MAX_REMARK_LENGTH = 1000
UNLIMITED_MINIMUM = 10
SIMULATED_MAXIMUM = 100000
SENDABLE_STATUSES = {"active", "ask_first", "warning"}


@dataclass
class PreparedSync:
    payload: dict[str, Any]
    category_name: str
    parsed_count: int
    sent_count: int
    merged_count: int
    warnings: list[str]


class QuoteSyncValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("；".join(errors))
        self.errors = errors


def prepare_sync_payload(
    *,
    merchant: dict[str, Any],
    rows: list[dict[str, Any]],
    category_settings: dict[str, dict[str, Any]],
    country_mappings: dict[str, str],
) -> PreparedSync:
    source_rows = [row for row in rows if not row.get("deleted")]
    errors: list[str] = []
    warnings: list[str] = []
    if not merchant:
        errors.append("请先选择 Cardsabi 商家。")
    if not source_rows:
        errors.append("没有可发送的解析结果。")

    missing_brand_lines = [
        str(row.get("line_no") or index)
        for index, row in enumerate(source_rows, start=1)
        if not str(row.get("brand") or "").strip()
    ]
    if missing_brand_lines:
        errors.append(f"第{'、'.join(missing_brand_lines)}行缺少品牌。")
    brands = {str(row.get("brand") or "").strip() for row in source_rows if str(row.get("brand") or "").strip()}
    if len(brands) != 1:
        if not brands:
            errors.append("本次报价没有确认品牌。")
        else:
            errors.append(f"本次包含多个品牌：{'、'.join(sorted(brands))}。每次只能发送一个品牌。")
    if errors:
        raise QuoteSyncValidationError(errors)

    category_name = next(iter(brands))
    category_setting = category_settings.get(category_name) or {}
    card_speed = str(category_setting.get("card_speed") or "").strip()
    if category_name not in category_settings:
        errors.append(f"Cardsabi 品牌 {category_name} 已不存在或已停用。")
    if card_speed not in {"Fast", "Slow"}:
        errors.append(f"Cardsabi 品牌 {category_name} 尚未配置卡速 Fast/Slow。")

    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows, start=1):
        line_label = f"第{row.get('line_no') or index}行"
        row_brand = str(row.get("brand") or "").strip()
        if row_brand != category_name:
            errors.append(f"{line_label}品牌与本批品牌 {category_name} 不一致。")
            continue
        status = str(row.get("status") or "active").strip()
        if status not in SENDABLE_STATUSES:
            errors.append(
                f"{line_label}状态为{status_label(status)}。请先在 Cardsabi 后台人工处理，"
                "再从本批删除或改正该行；系统不会自动关闭报价。"
            )
            continue
        try:
            candidates.append(
                _prepare_row(
                    row,
                    line_label=line_label,
                    category_name=category_name,
                    card_speed=card_speed,
                    country_mappings=country_mappings,
                )
            )
        except ValueError as exc:
            errors.append(f"{line_label}：{exc}")

    if not candidates and not errors:
        errors.append("没有状态正常且价格明确的报价可以发送。")
    if errors:
        raise QuoteSyncValidationError(errors)

    merged_items = _merge_candidates(candidates, errors)
    if errors:
        raise QuoteSyncValidationError(errors)

    quote_list = [item["payload"] for item in merged_items]
    payload = {
        "merchantQuoteList": [
            {
                "merchantNumber": merchant["merchant_number"],
                "merchantName": merchant["merchant_name"],
                "quoteList": quote_list,
            }
        ]
    }
    return PreparedSync(
        payload=payload,
        category_name=category_name,
        parsed_count=len(source_rows),
        sent_count=len(quote_list),
        merged_count=len(candidates) - len(quote_list),
        warnings=warnings,
    )


def _prepare_row(
    row: dict[str, Any],
    *,
    line_label: str,
    category_name: str,
    card_speed: str,
    country_mappings: dict[str, str],
) -> dict[str, Any]:
    country = str(row.get("country") or "").strip()
    cardsabi_country = country_mappings.get(country, "")
    if not cardsabi_country:
        raise ValueError(f"国家 {country or '待确认'} 尚未映射到 Cardsabi 国家。")

    card_type = _card_type(row)
    rate = _decimal(row.get("supplier_rate"), "供应商报价")
    if rate < 0:
        raise ValueError("供应商报价不能为负数。")
    if max(0, -rate.as_tuple().exponent) > 15:
        raise ValueError("供应商报价最多允许15位小数。")

    minimum, maximum, multiple, denomination_type = _denomination(row)
    remark = _base_remark(row)
    if len(remark) > MAX_REMARK_LENGTH:
        raise ValueError(f"商家备注超过{MAX_REMARK_LENGTH}个字符。")

    payload: dict[str, Any] = {
        "categoryName": category_name,
        "cardType": card_type,
        "country": cardsabi_country,
        "price": str(rate),
        "cardSpeed": card_speed,
        "minimum": minimum,
        "maximum": maximum,
    }
    bin_value = str(row.get("bin") or "").strip()
    if bin_value:
        payload["bin"] = bin_value
    payload["merchantRemark"] = remark or "-"
    if multiple is not None:
        payload["multipleValue"] = multiple

    raw_subtype = str(row.get("raw_card_subtype") or row.get("subtype") or "").strip()
    return {
        "payload": payload,
        "rate": rate,
        "raw_subtype": raw_subtype,
        "line_label": line_label,
        "denomination_type": denomination_type,
        "key": (
            category_name,
            cardsabi_country,
            card_type,
            bin_value,
            minimum,
            maximum,
            denomination_type,
            multiple,
        ),
    }


def _merge_candidates(candidates: list[dict[str, Any]], errors: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate["key"], []).append(candidate)

    result: list[dict[str, Any]] = []
    for group in grouped.values():
        selected = min(group, key=lambda item: item["rate"])
        payload = dict(selected["payload"])
        remarks = [str(item["payload"].get("merchantRemark") or "").strip() for item in group]
        unique_remarks = list(dict.fromkeys(item for item in remarks if item and item != "-"))
        if len(group) > 1:
            details = list(
                dict.fromkeys(
                    f"{item['raw_subtype'] or item['payload']['cardType']}{item['payload']['price']}"
                    for item in group
                )
            )
            merge_note = (
                f"原始报价：{'、'.join(details)}；合并为{payload['cardType']}后"
                f"按较低价{payload['price']}发送"
            )
            unique_remarks.append(merge_note)
        remark = "；".join(unique_remarks)
        if len(remark) > MAX_REMARK_LENGTH:
            errors.append(
                f"{selected['line_label']}：合并后的商家备注超过{MAX_REMARK_LENGTH}个字符。"
            )
        elif remark:
            payload["merchantRemark"] = remark
        else:
            payload["merchantRemark"] = "-"
        result.append({**selected, "payload": payload})
    return result


def _card_type(row: dict[str, Any]) -> str:
    explicit = str(row.get("cardsabi_card_type") or "").strip()
    if explicit:
        if explicit not in {"Physical", "Code", "ECode"}:
            raise ValueError("Cardsabi 卡类型只能是 Physical、Code 或 ECode。")
        return explicit
    brand = str(row.get("brand") or "").strip()
    frontend_type = str(row.get("frontend_type") or "").strip().lower()
    raw_subtype = str(row.get("raw_card_subtype") or row.get("subtype") or "").strip()
    normalized = normalize_card_subtype_for_brand(
        brand,
        str(row.get("normalized_card_subtype") or raw_subtype),
        frontend_type,
    )
    if normalized == "电子卡" or "电子" in raw_subtype:
        return "ECode"
    if frontend_type == "code" or normalized == "代码":
        return "Code"
    if frontend_type == "physical" or normalized in {"卡图", "竖卡"}:
        return "Physical"
    raise ValueError("卡类型未确认，无法转换为 Physical、Code 或 ECode。")


def _denomination(row: dict[str, Any]) -> tuple[int, int, int | None, str]:
    minimum = _optional_int(row.get("denom_min"), "面额下限")
    maximum = _optional_int(row.get("denom_max"), "面额上限")
    multiple = _optional_int(row.get("multiplier"), "倍数")
    if multiple is not None and multiple <= 0:
        raise ValueError("倍数必须大于0。")

    if minimum is None and maximum is None:
        if multiple:
            minimum = ceil(UNLIMITED_MINIMUM / multiple) * multiple
            maximum = floor(SIMULATED_MAXIMUM / multiple) * multiple
        else:
            minimum, maximum = UNLIMITED_MINIMUM, SIMULATED_MAXIMUM
    elif minimum is not None and maximum is None:
        maximum = SIMULATED_MAXIMUM
    elif minimum is None:
        raise ValueError("面额范围只有上限，没有下限。")

    if minimum <= 0 or maximum <= 0 or minimum > maximum:
        raise ValueError("面额上下限必须为正整数，且下限不能大于上限。")
    if minimum == maximum:
        return minimum, maximum, None, "FIXED"
    if multiple is None:
        return minimum, maximum, None, "RANGE"
    if minimum < multiple or minimum % multiple != 0 or maximum % multiple != 0:
        raise ValueError("倍数面额要求上下限能被倍数整除，且下限不能小于倍数。")
    return minimum, maximum, multiple, "MULTIPLE"


def _base_remark(row: dict[str, Any]) -> str:
    parts: list[str] = []
    processing_method = str(row.get("processing_method") or "").strip()
    if processing_method:
        parts.append(f"处理方式：{method_label(processing_method)}")
    feedback = str(row.get("feedback_note") or "").strip()
    if feedback:
        parts.append(f"反馈时间：{feedback}")
    status = str(row.get("status") or "active").strip()
    if status != "active":
        parts.append(f"状态：{status_label(status)}")
    requirements = str(row.get("requirements") or "").strip()
    if requirements:
        parts.append(f"对接群备注：{requirements}")
    return "；".join(dict.fromkeys(parts))


def _decimal(value: Any, label: str) -> Decimal:
    if value in (None, ""):
        raise ValueError(f"{label}不能为空。")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}格式错误。") from exc


def _optional_int(value: Any, label: str) -> int | None:
    if value in (None, ""):
        return None
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise ValueError(f"{label}必须是整数。")
    return int(number)
