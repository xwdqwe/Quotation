from __future__ import annotations

import secrets
import os
import re
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_auth_settings,
    safe_next_path,
    session_username,
    validate_auth_configuration,
    verify_password,
)
from .cardsabi_client import CardsabiClient, CardsabiClientError, get_cardsabi_settings
from .database import get_connection, init_db, list_active_markets
from .money import decimal_text
from .parsing import method_label, parse_quote_text, status_label, subtype_options
from .quote_sync import QuoteSyncValidationError, prepare_sync_payload
from .standards import market_label, market_value, split_market_value
from .sync_store import (
    brand_mapping_dict,
    category_setting_dict,
    catalog_status,
    cleanup_sync_history,
    country_mapping_dict,
    get_merchant,
    init_sync_tables,
    list_brand_mappings,
    list_categories,
    list_category_settings,
    list_countries,
    list_country_mappings,
    list_merchants,
    list_sync_history,
    record_sync_history,
    replace_catalogs,
    save_category_settings,
    save_brand_mappings,
    save_country_mappings,
)


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_local_env() -> None:
    path = BASE_DIR / ".env.local"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()

app = FastAPI(title="Cardsabi 报价解析器")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
templates.env.filters["fmt"] = lambda value: format_number(value)
templates.env.globals["method_label"] = method_label
templates.env.globals["status_label"] = status_label
templates.env.globals["subtype_options"] = subtype_options
templates.env.globals["market_value"] = market_value
templates.env.globals["market_label"] = market_label


class QuoteRowPayload(BaseModel):
    line_no: int | None = None
    source_line: str = ""
    source_text: str = ""
    parse_note: str = ""
    brand: str = ""
    market: str = ""
    country: str = ""
    currency: str = ""
    frontend_type: str = ""
    cardsabi_card_type: str = ""
    subtype: str = ""
    raw_card_subtype: str = ""
    normalized_card_subtype: str = ""
    processing_method: str = "fast_card"
    feedback_note: str = ""
    bin: str = ""
    multiplier: Decimal | None = None
    denom_min: Decimal | None = None
    denom_max: Decimal | None = None
    range_type: str = ""
    supplier_rate: Decimal | None = None
    status: str = "active"
    requirements: str = ""
    confidence: float | None = 0.5
    deleted: bool = False


class QuoteSyncPayload(BaseModel):
    merchant_number: str = ""
    operator: str = ""
    source_text: str = ""
    rows: list[QuoteRowPayload] = Field(default_factory=list)


class BinOptionsPayload(BaseModel):
    category_name: str = ""


@app.middleware("http")
async def require_login(request: Request, call_next):
    settings = get_auth_settings()
    request.state.auth_enabled = settings.enabled
    request.state.auth_username = ""
    if not settings.enabled or request.url.path == "/login" or request.url.path.startswith("/static/"):
        return await call_next(request)

    username = session_username(request.cookies.get(SESSION_COOKIE_NAME, ""), settings)
    if username:
        request.state.auth_username = username
        return await call_next(request)

    query = f"?{request.url.query}" if request.url.query else ""
    next_path = safe_next_path(request.url.path + query)
    content_type = request.headers.get("content-type", "")
    if request.method == "GET" or "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        return RedirectResponse(f"/login?next={url_quote(next_path)}", status_code=303)
    return JSONResponse({"detail": "登录已过期，请重新登录。"}, status_code=401)


@app.on_event("startup")
def startup() -> None:
    validate_auth_configuration()
    init_db(seed=False)
    with closing(get_connection()) as conn, conn:
        init_sync_tables(conn)
        cleanup_sync_history(conn)


@app.get("/login")
def login_page(request: Request, next: str = "/", error: str = ""):
    settings = get_auth_settings()
    if not settings.enabled:
        return RedirectResponse("/", status_code=303)
    if session_username(request.cookies.get(SESSION_COOKIE_NAME, ""), settings):
        return RedirectResponse(safe_next_path(next), status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next_path": safe_next_path(next), "error": error})


@app.post("/login")
async def login_submit(request: Request):
    settings = get_auth_settings()
    if not settings.enabled:
        return RedirectResponse("/", status_code=303)
    form = await _read_large_form(request)
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    next_path = safe_next_path(str(form.get("next", "/")))
    valid_username = secrets.compare_digest(username.encode("utf-8"), settings.username.encode("utf-8"))
    if not valid_username or not verify_password(password, settings.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next_path": next_path, "error": "账号或密码错误，请重新输入。"},
            status_code=401,
        )
    response = RedirectResponse(next_path, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(settings.username, settings),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@app.get("/")
def home(request: Request):
    with closing(get_connection()) as conn, conn:
        status = catalog_status(conn)
        recent = list_sync_history(conn, limit=5)
    return render(request, "index.html", {"catalog_status": status, "recent_history": recent})


@app.get("/quotes")
def quote_page(
    request: Request,
    merchant_number: str = "",
    sent: int = 0,
    sent_count: int = 0,
    merged_count: int = 0,
    response_message: str = "",
):
    with closing(get_connection()) as conn, conn:
        context = _quote_context(conn)
    return render(
        request,
        "quotes.html",
        {
            **context,
            "parsed_rows": [],
            "ignored_items": [],
            "source_text": "",
            "merchant_number": merchant_number,
            "operator": "",
            "default_brand": "",
            "default_market": "",
            "default_processing_method": "",
            "default_multiplier": "",
            "default_subtype": "",
            "pause_text_detected": False,
            "sent": bool(sent),
            "sent_count": sent_count,
            "merged_count": merged_count,
            "response_message": response_message,
        },
    )


@app.post("/quotes/parse")
async def parse_quotes(request: Request):
    form = await _read_large_form(request)
    merchant_number = str(form.get("merchant_number", "")).strip()
    operator = str(form.get("operator", "")).strip()
    source_text = str(form.get("source_text", ""))
    default_brand = str(form.get("default_brand", "")).strip()
    default_market = str(form.get("default_market", "")).strip()
    default_processing_method = str(form.get("default_processing_method", "")).strip()
    default_multiplier_raw = str(form.get("default_multiplier", "")).strip()
    default_multiplier = _to_float(default_multiplier_raw)
    default_subtype = str(form.get("default_subtype", "")).strip()
    ignored_items: list[str] = []
    with closing(get_connection()) as conn, conn:
        context = _quote_context(conn)
    categories = [item["name"] for item in context["brand_options"]]
    effective_default_brand = default_brand or _detect_official_category(source_text, categories)
    parsed_rows = parse_quote_text(
        merchant_number,
        source_text,
        24,
        default_brand=effective_default_brand,
        default_market=default_market,
        default_processing_method=default_processing_method,
        default_multiplier=default_multiplier,
        default_subtype=default_subtype,
        ignored_items=ignored_items,
    )
    _resolve_parsed_categories(
        parsed_rows,
        categories=categories,
        brand_mappings=context["brand_mappings"],
    )
    return render(
        request,
        "quotes.html",
        {
            **context,
            "parsed_rows": parsed_rows,
            "ignored_items": ignored_items,
            "source_text": source_text,
            "merchant_number": merchant_number,
            "operator": operator,
            "default_brand": default_brand,
            "default_market": default_market,
            "default_processing_method": default_processing_method,
            "default_multiplier": default_multiplier_raw,
            "default_subtype": default_subtype,
            "pause_text_detected": "暂停" in source_text or "不可用" in source_text,
            "sent": False,
            "sent_count": 0,
            "merged_count": 0,
            "response_message": "",
        },
    )


@app.post("/quotes/bin-options")
def quote_bin_options(payload: BinOptionsPayload):
    category_name = payload.category_name.strip()
    if not category_name:
        raise HTTPException(status_code=400, detail={"message": "请先选择 Cardsabi 品牌。"})
    try:
        bins = CardsabiClient().query_bins(category_name)
    except CardsabiClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": f"Cardsabi BIN 列表查询失败：{exc}"},
        ) from exc
    return {"category_name": category_name, "bins": bins}


@app.post("/quotes/send-json")
def send_quotes_json(payload: QuoteSyncPayload):
    merchant_number = payload.merchant_number.strip()
    rows = [_row_dict(row) for row in payload.rows]
    client = CardsabiClient()
    with closing(get_connection()) as conn, conn:
        try:
            _refresh_cardsabi_catalogs(conn, client)
            conn.commit()
        except (CardsabiClientError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": f"Cardsabi 实时目录刷新失败，已停止发送：{exc}。"
                    "请检查接口连接后重试，系统不会使用旧缓存继续发送。"
                },
            ) from exc

        merchant = get_merchant(conn, merchant_number)
        try:
            prepared = prepare_sync_payload(
                merchant=merchant or {},
                rows=rows,
                category_settings=category_setting_dict(conn),
                country_mappings=country_mapping_dict(conn),
            )
        except QuoteSyncValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors) from exc

        try:
            live_bins = client.query_bins(prepared.category_name)
        except CardsabiClientError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": f"Cardsabi 最新 BIN 列表查询失败，已停止发送：{exc}。"
                    "系统不会使用旧 BIN 继续发送。"
                },
            ) from exc
        selected_bins = {
            str(item.get("bin") or "").strip()
            for item in prepared.payload["merchantQuoteList"][0]["quoteList"]
            if str(item.get("bin") or "").strip()
        }
        invalid_bins = sorted(selected_bins - set(live_bins))
        if invalid_bins:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": (
                        f"品牌 {prepared.category_name} 选择的 BIN（{'、'.join(invalid_bins)}）"
                        "不在 Cardsabi 最新 BIN 列表中，请重新选择后发送。"
                    )
                },
            )

        try:
            response = client.submit_quotes(prepared.payload)
        except CardsabiClientError as exc:
            history_id = record_sync_history(
                conn,
                merchant_number=merchant_number,
                merchant_name=(merchant or {}).get("merchant_name", ""),
                category_name=prepared.category_name,
                source_text=payload.source_text,
                request_payload=prepared.payload,
                response_code="CONNECTION_ERROR",
                response_message=str(exc),
                status="failed",
                operator=payload.operator,
                parsed_count=prepared.parsed_count,
                sent_count=prepared.sent_count,
            )
            conn.commit()
            raise HTTPException(status_code=502, detail={"message": str(exc), "history_id": history_id}) from exc

        response_code = str(response.get("code") or "")
        response_message = str(response.get("message") or "")
        success = response_code == "00000"
        history_id = record_sync_history(
            conn,
            merchant_number=merchant_number,
            merchant_name=merchant["merchant_name"],
            category_name=prepared.category_name,
            source_text=payload.source_text,
            request_payload=prepared.payload,
            response_code=response_code,
            response_message=response_message,
            status="success" if success else "failed",
            operator=payload.operator,
            parsed_count=prepared.parsed_count,
            sent_count=prepared.sent_count,
        )
        if not success:
            conn.commit()
            raise HTTPException(
                status_code=502,
                detail={
                    "message": f"Cardsabi 返回 {response_code or '-'}：{response_message or '未知错误'}",
                    "history_id": history_id,
                },
            )
        return {
            "ok": True,
            "message": response_message or "成功",
            "history_id": history_id,
            "parsed_count": prepared.parsed_count,
            "sent_count": prepared.sent_count,
            "merged_count": prepared.merged_count,
            "warnings": prepared.warnings,
        }


@app.get("/settings")
def settings_page(request: Request, message: str = "", error: str = ""):
    settings = get_cardsabi_settings()
    with closing(get_connection()) as conn, conn:
        if settings.configured:
            try:
                _refresh_cardsabi_catalogs(conn, CardsabiClient(settings))
            except (CardsabiClientError, ValueError) as exc:
                error = error or f"Cardsabi 实时目录刷新失败：{exc}"
        context = {
            "api_settings": settings,
            "catalog_status": catalog_status(conn),
            "categories": list_categories(conn),
            "countries": list_countries(conn),
            "category_settings": list_category_settings(conn),
            "brand_mappings": list_brand_mappings(conn),
            "country_mappings": list_country_mappings(conn),
            "message": message,
            "error": error,
        }
    return render(request, "settings.html", context)


@app.post("/settings/refresh-catalogs")
def refresh_catalogs():
    try:
        client = CardsabiClient()
        with closing(get_connection()) as conn, conn:
            merchants, categories, countries = _refresh_cardsabi_catalogs(conn, client)
        message = f"已同步 {len(merchants)} 个商家、{len(categories)} 个品牌、{len(countries)} 个国家。"
        return RedirectResponse(f"/settings?message={url_quote(message)}", status_code=303)
    except (CardsabiClientError, ValueError) as exc:
        return RedirectResponse(f"/settings?error={url_quote(str(exc))}", status_code=303)


@app.post("/settings/save-mappings")
async def save_mappings(request: Request):
    form = await _read_large_form(request)
    category_rows = [
        {
            "category_name": str(form.get(f"official_category_name_{index}", "")),
            "card_speed": str(form.get(f"official_card_speed_{index}", "")),
        }
        for index in range(_to_int(form.get("category_row_count"), 0))
    ]
    brand_rows = [
        {
            "parser_brand": str(form.get(f"parser_brand_{index}", "")),
            "category_name": str(form.get(f"category_name_{index}", "")),
        }
        for index in range(_to_int(form.get("brand_row_count"), 0))
    ]
    country_rows = [
        {
            "parser_country": str(form.get(f"parser_country_{index}", "")),
            "cardsabi_country": str(form.get(f"cardsabi_country_{index}", "")),
        }
        for index in range(_to_int(form.get("country_row_count"), 0))
    ]
    try:
        with closing(get_connection()) as conn, conn:
            save_category_settings(conn, category_rows)
            save_brand_mappings(conn, brand_rows)
            save_country_mappings(conn, country_rows)
    except ValueError as exc:
        return RedirectResponse(f"/settings?error={url_quote(str(exc))}", status_code=303)
    return RedirectResponse("/settings?message=" + url_quote("映射设置已保存。"), status_code=303)


@app.get("/history")
def history_page(request: Request):
    with closing(get_connection()) as conn, conn:
        history = list_sync_history(conn)
    return render(request, "history.html", {"history": history})


@app.get("/match")
@app.get("/library")
@app.get("/app-categories")
def retired_page():
    return RedirectResponse("/quotes", status_code=303)


def _quote_context(conn: Any, *, refresh_live: bool = True) -> dict[str, Any]:
    catalog_refresh_error = ""
    settings = get_cardsabi_settings()
    if refresh_live and settings.configured:
        try:
            _refresh_cardsabi_catalogs(conn, CardsabiClient(settings))
        except (CardsabiClientError, ValueError) as exc:
            catalog_refresh_error = str(exc)
    return {
        "brand_options": [{"name": category} for category in list_categories(conn)],
        "market_options": list_active_markets(conn),
        "merchant_options": list_merchants(conn),
        "brand_mappings": brand_mapping_dict(conn),
        "catalog_status": catalog_status(conn),
        "api_configured": settings.configured,
        "catalog_refresh_error": catalog_refresh_error,
    }


def _resolve_parsed_categories(
    rows: list[dict[str, Any]],
    *,
    categories: list[str],
    brand_mappings: dict[str, dict[str, Any]],
) -> None:
    category_lookup = {category.casefold(): category for category in categories}
    for row in rows:
        parsed_brand = str(row.get("brand") or "").strip()
        mapping = brand_mappings.get(parsed_brand) or {}
        mapped_category = str(mapping.get("category_name") or "").strip()
        category_name = category_lookup.get(mapped_category.casefold()) if mapped_category else None
        if not category_name:
            category_name = category_lookup.get(parsed_brand.casefold())
        if category_name and category_name != parsed_brand:
            note = str(row.get("parse_note") or "").strip()
            row["parse_note"] = "；".join(item for item in [note, f"解析品牌 {parsed_brand} 映射为 {category_name}"] if item)
        row["brand"] = category_name or ""


def _detect_official_category(source_text: str, categories: list[str]) -> str:
    matches: list[str] = []
    for category in sorted(categories, key=len, reverse=True):
        pattern = re.escape(category).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![\w]){pattern}(?![\w])", source_text, re.IGNORECASE):
            matches.append(category)
    return matches[0] if len(matches) == 1 else ""


def _refresh_cardsabi_catalogs(conn: Any, client: CardsabiClient) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    merchants = client.query_merchants()
    categories = client.query_categories()
    countries = client.query_countries()
    replace_catalogs(conn, merchants, categories, countries)
    return merchants, categories, countries


def _row_dict(row: QuoteRowPayload) -> dict[str, Any]:
    result = row.model_dump()
    country, currency = split_market_value(row.market)
    if not country:
        country = row.country.strip()
        currency = row.currency.strip().upper()
    result["country"] = country
    result["currency"] = currency
    result["raw_card_subtype"] = row.raw_card_subtype.strip() or row.subtype.strip()
    return result


def render(request: Request, template_name: str, context: dict[str, Any]):
    view_context = {
        "auth_enabled": getattr(request.state, "auth_enabled", False),
        "auth_username": getattr(request.state, "auth_username", ""),
        **context,
    }
    return templates.TemplateResponse(request, template_name, view_context)


async def _read_large_form(request: Request):
    try:
        return await request.form(max_fields=20000)
    except TypeError:
        return await request.form()


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_number(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return decimal_text(value, str(value))
