from __future__ import annotations

import json
import secrets
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
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

from .database import (
    clear_test_data,
    bulk_update_quote_status,
    count_filtered_supplier_quotes,
    get_connection,
    init_db,
    list_filtered_supplier_quotes,
    list_active_brands,
    list_active_markets,
    list_supplier_groups,
    revoke_quote_batch,
    transition_supplier_group,
)
from .app_categories import (
    delete_app_category,
    export_app_categories_csv,
    get_app_category,
    import_app_categories_csv,
    list_app_categories,
    parse_app_category_names,
    save_app_category,
    save_app_categories_bulk,
    set_app_category_status,
)
from .matching import find_matches, log_match, normalize_match_form
from .money import decimal_text, to_decimal
from .parsing import method_label, normalized_subtype_options, parse_quote_text, status_label, subtype_options
from .pricing import bulk_confirm_app_prices, confirm_app_price, defer_app_price, list_app_prices, recalculate_app_prices
from .quote_service import analyze_quote_rows, analyze_supersede_preview, save_quote_batch
from .standards import (
    MATCH_SUBTYPE_OPTIONS,
    RAW_CARD_SUBTYPE_OPTIONS,
    is_open_ended_range,
    market_label,
    market_value,
    normalize_card_subtype_for_brand,
    normalized_subtype_options_for_brand,
    split_market_value,
)


BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Cardsabi 报价引擎")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
templates.env.filters["fmt"] = lambda value: format_number(value)
templates.env.globals["method_label"] = method_label
templates.env.globals["status_label"] = status_label
templates.env.globals["subtype_options"] = subtype_options
templates.env.globals["normalized_subtype_options"] = normalized_subtype_options
templates.env.globals["match_subtype_options"] = lambda: MATCH_SUBTYPE_OPTIONS
templates.env.globals["normalized_subtype_options_for_brand"] = normalized_subtype_options_for_brand
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
    subtype: str = ""
    raw_card_subtype: str = ""
    normalized_card_subtype: str = ""
    processing_method: str = "fast_card"
    feedback_note: str = ""
    multiplier: float | None = None
    denom_min: float | None = None
    denom_max: float | None = None
    range_type: str = ""
    supplier_rate: Decimal | None = None
    status: str = "active"
    requirements: str = ""
    confidence: float | None = 0.5
    received_at: str = ""
    expires_at: str = ""
    deleted: bool = False


class QuoteSavePayload(BaseModel):
    supplier_group: str = ""
    operator: str = ""
    confirm_safe_only: bool = False
    confirm_supersede: bool = False
    rows: list[QuoteRowPayload] = Field(default_factory=list)


class LibraryBulkActionPayload(BaseModel):
    mode: str = "selected"
    quote_ids: list[int] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    operator: str = "local_admin"
    force_confirm: bool = False


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
    with get_connection() as conn:
        recalculate_app_prices(conn)


@app.get("/login")
def login_page(request: Request, next: str = "/", error: str = ""):
    settings = get_auth_settings()
    if not settings.enabled:
        return RedirectResponse("/", status_code=303)
    if session_username(request.cookies.get(SESSION_COOKIE_NAME, ""), settings):
        return RedirectResponse(safe_next_path(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_path": safe_next_path(next), "error": error},
    )


@app.post("/login")
async def login_submit(request: Request):
    settings = get_auth_settings()
    if not settings.enabled:
        return RedirectResponse("/", status_code=303)
    form = await _read_large_form(request)
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    next_path = safe_next_path(str(form.get("next", "/")))
    if not secrets.compare_digest(username.encode("utf-8"), settings.username.encode("utf-8")) or not verify_password(
        password, settings.password_hash
    ):
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
    return render(request, "index.html", {})


@app.get("/quotes")
def quote_page(
    request: Request,
    tab: str = "needs",
    supplier_group: str = "",
    operator: str = "",
    saved: int = 0,
    saved_count: int = 0,
    batch_id: str = "",
    manual_count: int = 0,
    revoked: int = 0,
    referenced_count: int = 0,
    pause_done: int = 0,
    pause_group: str = "",
    pause_brand: str = "",
    pause_count: int = 0,
    pause_log_id: int = 0,
    app_confirmed_count: int = 0,
):
    with get_connection() as conn:
        app_prices = list_app_prices(conn, tab)
        pending_suggestion_count = len(list_app_prices(conn, "needs"))
        standards = _standard_options(conn)
        batch = (
            conn.execute("SELECT * FROM quote_batches WHERE quote_batch_id = ?", (batch_id,)).fetchone()
            if batch_id
            else None
        )
        pause_result = None
        if pause_log_id:
            pause_log = conn.execute(
                "SELECT * FROM quote_status_logs WHERE id = ? AND action = 'pause_brand'",
                (pause_log_id,),
            ).fetchone()
            if pause_log:
                try:
                    pause_detail = json.loads(pause_log["note"] or "{}")
                except json.JSONDecodeError:
                    pause_detail = {}
                pause_result = {
                    "log_id": pause_log["id"],
                    "supplier_group": pause_log["supplier_group"],
                    "brand": pause_log["brand"],
                    "affected_count": pause_log["affected_count"],
                    **pause_detail,
                }
        if pause_result:
            pause_group = pause_result["supplier_group"]
            pause_brand = pause_result["brand"]
            pause_count = pause_result["affected_count"]
    return render(
        request,
        "quotes.html",
        {
            "parsed_rows": [],
            "ignored_items": [],
            "source_text": "",
            "supplier_group": supplier_group,
            "operator": operator,
            "default_expire_hours": 24,
            "default_brand": "",
            "default_market": "",
            "default_processing_method": "",
            "default_multiplier": "",
            "default_subtype": "",
            "app_prices": app_prices,
            "tab": tab,
            "batch_id": batch_id,
            "saved": bool(saved or saved_count),
            "saved_count": saved_count,
            "saved_batch": dict(batch) if batch else None,
            "manual_count": manual_count,
            "revoked": bool(revoked),
            "referenced_count": referenced_count,
            "pause_done": bool(pause_done),
            "pause_group": pause_group,
            "pause_brand": pause_brand,
            "pause_count": pause_count,
            "pause_result": pause_result,
            "app_confirmed_count": app_confirmed_count,
            "app_bulk_confirm_count": sum(
                1 for record in app_prices if record["status"] == "pending"
                and record["suggested_backend_rate"] is not None
            ),
            "pending_suggestion_count": pending_suggestion_count,
            "pause_text_detected": False,
            **standards,
        },
    )


@app.post("/quotes/parse")
async def parse_quotes(request: Request):
    form = await _read_large_form(request)
    supplier_group = str(form.get("supplier_group", "")).strip()
    operator = str(form.get("operator", "")).strip()
    source_text = str(form.get("source_text", ""))
    default_expire_hours = _to_float(form.get("default_expire_hours"), 24) or 24
    default_brand = str(form.get("default_brand", "")).strip()
    default_market = str(form.get("default_market", "")).strip()
    default_processing_method = str(form.get("default_processing_method", "")).strip()
    default_multiplier_raw = str(form.get("default_multiplier", "")).strip()
    default_multiplier = _to_float(default_multiplier_raw)
    default_subtype = str(form.get("default_subtype", "")).strip()
    ignored_items: list[str] = []
    parsed_rows = parse_quote_text(
        supplier_group,
        source_text,
        default_expire_hours,
        default_brand=default_brand,
        default_market=default_market,
        default_processing_method=default_processing_method,
        default_multiplier=default_multiplier,
        default_subtype=default_subtype,
        ignored_items=ignored_items,
    )

    with get_connection() as conn:
        app_prices = list_app_prices(conn, "needs")
        pending_suggestion_count = len(app_prices)
        standards = _standard_options(conn)

    return render(
        request,
        "quotes.html",
        {
            "parsed_rows": parsed_rows,
            "ignored_items": ignored_items,
            "source_text": source_text,
            "supplier_group": supplier_group,
            "operator": operator,
            "default_expire_hours": default_expire_hours,
            "default_brand": default_brand,
            "default_market": default_market,
            "default_processing_method": default_processing_method,
            "default_multiplier": default_multiplier_raw,
            "default_subtype": default_subtype,
            "app_prices": app_prices,
            "tab": "needs",
            "batch_id": "",
            "saved": False,
            "saved_count": 0,
            "saved_batch": None,
            "manual_count": 0,
            "revoked": False,
            "referenced_count": 0,
            "pause_done": False,
            "pause_group": "",
            "pause_brand": "",
            "pause_count": 0,
            "pause_result": None,
            "app_confirmed_count": 0,
            "app_bulk_confirm_count": sum(
                1 for record in app_prices if record["status"] == "pending"
                and record["suggested_backend_rate"] is not None
            ),
            "pending_suggestion_count": pending_suggestion_count,
            "pause_text_detected": "暂停" in source_text,
            **standards,
        },
    )


@app.post("/quotes/save")
async def save_quotes(request: Request):
    form = await _read_large_form(request)
    row_count = int(form.get("row_count") or 0)
    quotes = []
    with get_connection() as conn:
        for index in range(row_count):
            if form.get(f"delete_{index}") == "on":
                continue
            quote = _quote_from_form(form, index)
            if _should_save_quote(quote):
                quotes.append(quote)
        result = save_quote_batch(conn, str(form.get("supplier_group", "")), quotes)
        recalculate_app_prices(
            conn,
            affected_quote_ids=result.get("affected_quote_ids") or result["inserted_ids"],
            affected_batch_id=result["quote_batch_id"],
        )
    return RedirectResponse(
        f"/quotes?saved=1&saved_count={result['saved_count']}&batch_id={result['quote_batch_id']}",
        status_code=303,
    )


@app.post("/quotes/save-json")
def save_quotes_json(payload: QuoteSavePayload):
    supplier_group = payload.supplier_group.strip()
    with get_connection() as conn:
        if payload.confirm_safe_only:
            if not supplier_group:
                raise HTTPException(status_code=400, detail={"message": "请先填写来源群/供应商。"})
            quotes = [_quote_from_payload(supplier_group, row) for row in payload.rows if not row.deleted]
        else:
            errors, quotes = _validated_quotes(conn, supplier_group, payload.rows)
            if errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "保存失败，请先修正以下问题。",
                        "errors": errors,
                    },
                )
        preview = analyze_supersede_preview(
            conn,
            supplier_group,
            quotes,
            safe_only=payload.confirm_safe_only,
        )
        if preview["supersede_quote_count"] > 0 and not payload.confirm_supersede:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "保存前需要先确认覆盖预览。",
                    "preview": preview,
                },
            )
        try:
            result = save_quote_batch(
                conn,
                supplier_group,
                quotes,
                operator=payload.operator.strip(),
                safe_only=payload.confirm_safe_only,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
        recalculate_app_prices(
            conn,
            affected_quote_ids=result.get("affected_quote_ids") or result["inserted_ids"],
            affected_batch_id=result["quote_batch_id"],
        )
    return {
        **result,
        "message": f"本次新增/更新 {result['saved_count']} 条报价，覆盖旧报价 {len(result.get('superseded_ids', []))} 条。",
        "redirect_url": (
            f"/quotes?saved=1&saved_count={result['saved_count']}"
            f"&batch_id={result['quote_batch_id']}&manual_count={result['manual_count']}"
        ),
    }


@app.post("/quotes/save-preview")
def save_quotes_preview(payload: QuoteSavePayload):
    supplier_group = payload.supplier_group.strip()
    with get_connection() as conn:
        if payload.confirm_safe_only:
            if not supplier_group:
                raise HTTPException(status_code=400, detail={"message": "请先填写来源群/供应商。"})
            quotes = [_quote_from_payload(supplier_group, row) for row in payload.rows if not row.deleted]
        else:
            errors, quotes = _validated_quotes(conn, supplier_group, payload.rows)
            if errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "保存前请先修正以下问题。",
                        "errors": errors,
                    },
                )
        return analyze_supersede_preview(
            conn,
            supplier_group,
            quotes,
            safe_only=payload.confirm_safe_only,
        )


@app.post("/quotes/confirm-preview")
def preview_quote_confirmation(payload: QuoteSavePayload):
    supplier_group = payload.supplier_group.strip()
    if not supplier_group:
        raise HTTPException(status_code=400, detail={"message": "请先填写来源群/供应商。"})
    quotes = [_quote_from_payload(supplier_group, row) for row in payload.rows if not row.deleted]
    with get_connection() as conn:
        return analyze_quote_rows(conn, supplier_group, quotes)


@app.post("/quote-batches/{quote_batch_id}/revoke")
async def revoke_batch(quote_batch_id: str, request: Request):
    form = await _read_large_form(request)
    operator = str(form.get("operator", "")).strip()
    reason = str(form.get("reason", "")).strip()
    with get_connection() as conn:
        try:
            result = revoke_quote_batch(conn, quote_batch_id, operator=operator, reason=reason)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        recalculate_app_prices(conn)
    return RedirectResponse(
        f"/quotes?revoked=1&batch_id={quote_batch_id}&referenced_count={result['referenced_count']}",
        status_code=303,
    )


@app.post("/app-prices/confirm-visible")
async def confirm_visible_app_prices(request: Request):
    form = await _read_large_form(request)
    tab = str(form.get("tab", "needs")).strip()
    operator = str(form.get("operator", "")).strip()
    batch_id = str(form.get("batch_id", "")).strip()
    if tab not in {"needs", "all"}:
        tab = "needs"
    with get_connection() as conn:
        confirmed_count = bulk_confirm_app_prices(
            conn,
            tab,
            operator=operator,
            affected_batch_id=None,
        )
    return RedirectResponse(
        f"/quotes?tab={tab}&batch_id={batch_id}&app_confirmed_count={confirmed_count}",
        status_code=303,
    )


@app.post("/app-prices/{record_id}/confirm")
async def confirm_price(record_id: int, request: Request):
    form = await _read_large_form(request)
    operator = str(form.get("operator", "")).strip()
    action = str(form.get("action", "confirm_update")).strip() or "confirm_update"
    with get_connection() as conn:
        confirm_app_price(conn, record_id, operator=operator, action=action)
    return RedirectResponse("/quotes?tab=needs", status_code=303)


@app.post("/app-prices/{record_id}/defer")
async def defer_price(record_id: int, request: Request):
    form = await _read_large_form(request)
    operator = str(form.get("operator", "")).strip()
    reason = str(form.get("reason", "暂不处理")).strip() or "暂不处理"
    with get_connection() as conn:
        defer_app_price(conn, record_id, operator=operator, reason=reason)
    return RedirectResponse("/quotes?tab=needs", status_code=303)


@app.get("/suggestions/pending")
def pending_suggestions():
    with get_connection() as conn:
        return {"suggestions": [dict(row) for row in list_app_prices(conn, "needs")]}


@app.get("/suggestions")
def suggestions(status: str = "pending"):
    tab = "needs" if status == "pending" else ("no_change" if status == "auto_closed_no_change" else "all")
    with get_connection() as conn:
        rows = [dict(row) for row in list_app_prices(conn, tab)]
    if status and tab == "all":
        rows = [row for row in rows if row.get("status") == status]
    return {"suggestions": rows}


@app.post("/suggestions/{suggestion_id}/sync-admin")
def sync_suggestion_admin(suggestion_id: int, payload: dict[str, Any] | None = None):
    operator = str((payload or {}).get("operator", "")).strip()
    with get_connection() as conn:
        confirm_app_price(conn, suggestion_id, operator=operator, action="confirm_update")
    return {"ok": True}


@app.post("/suggestions/{suggestion_id}/fill-zero")
def fill_suggestion_zero(suggestion_id: int, payload: dict[str, Any] | None = None):
    operator = str((payload or {}).get("operator", "")).strip()
    with get_connection() as conn:
        confirm_app_price(conn, suggestion_id, operator=operator, action="confirm_zero")
    return {"ok": True}


@app.post("/suggestions/{suggestion_id}/ignore")
def ignore_suggestion(suggestion_id: int, payload: dict[str, Any] | None = None):
    data = payload or {}
    operator = str(data.get("operator", "")).strip()
    reason = str(data.get("reason", "暂不处理")).strip() or "暂不处理"
    with get_connection() as conn:
        defer_app_price(conn, suggestion_id, operator=operator, reason=reason)
    return {"ok": True}


class SuggestionBulkPayload(BaseModel):
    suggestion_ids: list[int] = Field(default_factory=list)
    operator: str = ""


@app.post("/suggestions/bulk-sync-admin")
def bulk_sync_suggestions(payload: SuggestionBulkPayload):
    with get_connection() as conn:
        operator = payload.operator.strip()
        if not payload.suggestion_ids:
            count = bulk_confirm_app_prices(conn, "needs", operator=operator)
        else:
            count = 0
            for suggestion_id in payload.suggestion_ids:
                confirm_app_price(conn, int(suggestion_id), operator=operator, action="confirm_update")
                count += 1
    return {"ok": True, "confirmed_count": count}


@app.post("/admin/reset-test-data")
def reset_test_data():
    with get_connection() as conn:
        clear_test_data(conn)
        recalculate_app_prices(conn)
    return RedirectResponse("/library?reset=1", status_code=303)


@app.get("/app-categories")
def app_categories_page(
    request: Request,
    edit_id: int = 0,
    keyword: str = "",
    brand: str = "",
    market: str = "",
    app_card_type: str = "",
    normalized_subtype: str = "",
    status: str = "",
    message: str = "",
    error: str = "",
    import_success: int = 0,
    import_skip: int = 0,
    import_errors: str = "",
):
    filters = {
        "keyword": keyword.strip(),
        "brand": brand.strip(),
        "market": market.strip(),
        "app_card_type": app_card_type.strip(),
        "normalized_subtype": normalized_subtype.strip(),
        "status": status.strip(),
    }
    with get_connection() as conn:
        categories = list_app_categories(conn, filters)
        edit_category = get_app_category(conn, edit_id) if edit_id else None
        standards = _standard_options(conn)
    return render(
        request,
        "app_categories.html",
        {
            "filters": filters,
            "categories": categories,
            "edit_category": edit_category,
            "message": message,
            "error": error,
            "import_report": {
                "success_count": import_success,
                "skip_count": import_skip,
                "errors": import_errors.split("||") if import_errors else [],
            },
            "parsed_category_rows": [],
            "category_names_text": "",
            **standards,
        },
    )


@app.post("/app-categories/save")
async def save_app_category_route(request: Request):
    form = await _read_large_form(request)
    data = dict(form)
    with get_connection() as conn:
        try:
            category = save_app_category(conn, data)
        except ValueError as exc:
            return RedirectResponse(
                f"/app-categories?error={url_quote(str(exc))}",
                status_code=303,
            )
    return RedirectResponse(
        f"/app-categories?message={url_quote('APP 分类已保存')}&edit_id={category.get('id', 0)}",
        status_code=303,
    )


@app.post("/app-categories/parse-names")
async def parse_app_category_names_route(request: Request):
    form = await _read_large_form(request)
    category_names_text = str(form.get("category_names_text", "")).strip()
    with get_connection() as conn:
        parsed = parse_app_category_names(conn, category_names_text)
        categories = list_app_categories(conn, {})
        standards = _standard_options(conn)
    return render(
        request,
        "app_categories.html",
        {
            "filters": {
                "keyword": "",
                "brand": "",
                "market": "",
                "app_card_type": "",
                "normalized_subtype": "",
                "status": "",
            },
            "categories": categories,
            "edit_category": None,
            "message": f"本次解析出 {len(parsed['rows'])} 条分类记录",
            "error": "",
            "import_report": {"success_count": 0, "skip_count": 0, "errors": []},
            "parsed_category_rows": parsed["rows"],
            "ignored_category_items": parsed["ignored"],
            "category_names_text": category_names_text,
            **standards,
        },
    )


@app.post("/app-categories/save-parsed")
async def save_parsed_app_categories_route(request: Request):
    form = await _read_large_form(request)
    rows = _app_category_rows_from_form(form)
    with get_connection() as conn:
        report = save_app_categories_bulk(conn, rows)
    if report["errors"]:
        error_text = "；".join(
            f"第{item['line_no']}行：{item['reason']}" for item in report["errors"][:8]
        )
        return RedirectResponse(f"/app-categories?error={url_quote(error_text)}", status_code=303)
    message = f"分类已保存：新增 {report['created_count']} 条，更新 {report['updated_count']} 条"
    return RedirectResponse(f"/app-categories?message={url_quote(message)}", status_code=303)


@app.post("/app-categories/{category_id}/toggle")
async def toggle_app_category(category_id: int, request: Request):
    form = await _read_large_form(request)
    status = str(form.get("status", "")).strip()
    with get_connection() as conn:
        try:
            set_app_category_status(conn, category_id, status)
        except ValueError as exc:
            return RedirectResponse(f"/app-categories?error={url_quote(str(exc))}", status_code=303)
    return RedirectResponse("/app-categories?message=APP 分类状态已更新", status_code=303)


@app.post("/app-categories/{category_id}/delete")
async def delete_app_category_route(category_id: int):
    with get_connection() as conn:
        delete_app_category(conn, category_id)
    return RedirectResponse("/app-categories?message=APP 分类已删除", status_code=303)


@app.post("/app-categories/import")
async def import_app_categories(request: Request):
    form = await _read_large_form(request)
    upload = form.get("csv_file")
    if not upload or not hasattr(upload, "read"):
        return RedirectResponse("/app-categories?error=请选择 CSV 文件", status_code=303)
    content = await upload.read()
    csv_text = content.decode("utf-8-sig")
    with get_connection() as conn:
        report = import_app_categories_csv(conn, csv_text)
    error_text = "||".join(
        f"第{item['line_no']}行：{item['reason']}" for item in report["errors"][:5]
    )
    return RedirectResponse(
        (
            f"/app-categories?import_success={report['success_count']}"
            f"&import_skip={report['skip_count']}&import_errors={url_quote(error_text)}"
        ),
        status_code=303,
    )


@app.get("/app-categories/export")
def export_app_categories():
    with get_connection() as conn:
        csv_text = export_app_categories_csv(conn)
    return Response(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=app_categories.csv"},
    )


@app.get("/match")
def match_page(request: Request):
    with get_connection() as conn:
        standards = _standard_options(conn)
    return render(
        request,
        "match.html",
        {
            "query": {},
            "matches": None,
            **standards,
        },
    )


@app.post("/match")
async def run_match(request: Request):
    form = await _read_large_form(request)
    query = normalize_match_form(dict(form))
    with get_connection() as conn:
        matches = find_matches(conn, query)
        selected_id = matches["matches"][0]["id"] if matches["matches"] else None
        if not matches["errors"]:
            log_match(conn, query, selected_id)
        standards = _standard_options(conn)
    return render(
        request,
        "match.html",
        {
            "query": query,
            "matches": matches,
            **standards,
        },
    )


@app.get("/library")
def library_page(
    request: Request,
    reset: int = 0,
    group_message: str = "",
    group_error: str = "",
    group_log_id: int = 0,
    brand: str = "",
    market: str = "",
    country: str = "",
    currency: str = "",
    frontend_type: str = "",
    subtype: str = "",
    normalized_card_subtype: str = "",
    processing_method: str = "",
    supplier_group: str = "",
    status: str = "",
    denom_min: str = "",
    denom_max: str = "",
    multiplier: str = "",
    expired: str = "",
    quote_batch_id: str = "",
    include_history: str = "",
):
    market_country, market_currency = split_market_value(market)
    requested_subtype = (normalized_card_subtype or subtype).strip()
    filtered_subtype = (
        normalize_card_subtype_for_brand(brand, requested_subtype)
        if brand.strip() and requested_subtype
        else requested_subtype
    )
    filters = {
        "brand": brand.strip(),
        "country": market_country or country.strip(),
        "currency": market_currency or currency.strip().upper(),
        "market": market or market_value(country, currency),
        "frontend_type": frontend_type.strip(),
        "subtype": subtype.strip(),
        "normalized_card_subtype": filtered_subtype,
        "processing_method": processing_method.strip(),
        "supplier_group": supplier_group.strip(),
        "status": status.strip(),
        "denom_min": denom_min.strip(),
        "denom_max": denom_max.strip(),
        "multiplier": multiplier.strip(),
        "expired": expired.strip(),
        "quote_batch_id": quote_batch_id.strip(),
        "include_history": include_history.strip(),
    }
    with get_connection() as conn:
        quotes = list_filtered_supplier_quotes(conn, filters)
        filtered_quote_count = count_filtered_supplier_quotes(conn, filters)
        supplier_groups = list_supplier_groups(conn)
        operation_logs = conn.execute(
            "SELECT * FROM operation_logs ORDER BY id DESC LIMIT 100"
        ).fetchall()
        bulk_action_logs = conn.execute(
            "SELECT * FROM quote_bulk_action_logs ORDER BY id DESC LIMIT 100"
        ).fetchall()
        group_impact_result = None
        if group_log_id:
            group_log = conn.execute("SELECT * FROM operation_logs WHERE id = ?", (group_log_id,)).fetchone()
            if group_log:
                try:
                    details = json.loads(group_log["details"] or "{}")
                except json.JSONDecodeError:
                    details = {}
                group_impact_result = {
                    "action": group_log["action"],
                    "group_name": group_log["group_name"],
                    "old_status": group_log["old_status"],
                    "new_status": group_log["new_status"],
                    "operator": group_log["operator"],
                    "reason": group_log["reason"],
                    "impact_list": details.get("impact_list", []),
                }
        standards = _standard_options(conn)
    return render(
        request,
        "library.html",
        {
            "filters": filters,
            "quotes": quotes,
            "filtered_quote_count": filtered_quote_count,
            "reset": bool(reset),
            "supplier_groups": supplier_groups,
            "operation_logs": operation_logs,
            "bulk_action_logs": bulk_action_logs,
            "group_impact_result": group_impact_result,
            "group_message": group_message,
            "group_error": group_error,
            **standards,
        },
    )


@app.post("/supplier-groups/{group_id}/status")
async def change_supplier_group_status(group_id: int, request: Request):
    form = await _read_large_form(request)
    action = str(form.get("action", "")).strip()
    operator = str(form.get("operator", "")).strip()
    reason = str(form.get("reason", "")).strip()
    transitions = {
        "pause_group": "paused",
        "mark_group_needs_refresh": "needs_refresh",
        "confirm_reuse_old_quotes": "normal",
        "restore_group_normal": "normal",
    }
    new_status = transitions.get(action)
    if not new_status:
        raise HTTPException(status_code=400, detail="未知供应群操作")
    with get_connection() as conn:
        try:
            group = transition_supplier_group(
                conn,
                group_id,
                new_status,
                action,
                operator=operator,
                reason=reason,
            )
        except ValueError as exc:
            return RedirectResponse(
                f"/library?group_error={url_quote(str(exc))}",
                status_code=303,
            )
        recalculate_app_prices(conn)
    if action == "pause_group":
        message = f"{group['name']} 已暂停，报价已从匹配和 APP 建议报价中排除。"
    elif action == "mark_group_needs_refresh":
        message = f"{group['name']} 已解除暂停，但旧报价暂不参与匹配。请录入该群最新报价并确认后启用。"
    elif action == "confirm_reuse_old_quotes":
        message = f"{group['name']} 已确认沿用旧报价并恢复正常。"
    else:
        message = f"{group['name']} 已更新为 {new_status}"
    return RedirectResponse(
        f"/library?group_message={url_quote(message)}&group_log_id={group.get('operation_log_id', 0)}",
        status_code=303,
    )


@app.post("/library/quotes/bulk-pause")
def bulk_pause_library_quotes(payload: LibraryBulkActionPayload):
    return _run_library_bulk_quote_action("pause", payload)


@app.post("/library/quotes/bulk-resume")
def bulk_resume_library_quotes(payload: LibraryBulkActionPayload):
    return _run_library_bulk_quote_action("resume", payload)


def _run_library_bulk_quote_action(action: str, payload: LibraryBulkActionPayload) -> dict[str, Any]:
    with get_connection() as conn:
        try:
            result = bulk_update_quote_status(
                conn,
                action=action,
                mode=payload.mode,
                quote_ids=payload.quote_ids,
                filters=payload.filters,
                operator=payload.operator,
                reason=payload.reason,
                force_confirm=payload.force_confirm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
        if result["affected_quote_ids"]:
            recalculate_app_prices(conn, affected_quote_ids=result["affected_quote_ids"])
    return result


def list_supplier_quotes(conn, filters: dict[str, str]):
    clauses = []
    params: list[Any] = []
    exact_columns = [
        "brand",
        "country",
        "currency",
        "frontend_type",
        "normalized_card_subtype",
        "processing_method",
        "status",
    ]
    for column in exact_columns:
        if filters.get(column):
            clauses.append(f"q.{column} = ?")
            params.append(filters[column])
    if filters.get("supplier_group"):
        clauses.append("q.supplier_group LIKE ?")
        params.append(f"%{filters['supplier_group']}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(
        f"""
        SELECT q.*, COALESCE(g.status, 'normal') AS supplier_group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        {where}
        ORDER BY q.created_at DESC, q.id DESC
        LIMIT 300
        """,
        params,
    ).fetchall()


def render(request: Request, template_name: str, context: dict[str, Any]):
    view_context = {
        "auth_enabled": getattr(request.state, "auth_enabled", False),
        "auth_username": getattr(request.state, "auth_username", ""),
        **context,
    }
    return templates.TemplateResponse(request, template_name, view_context)


def _quote_from_form(form: Any, index: int) -> dict[str, Any]:
    country, currency = split_market_value(_field(form, index, "market"))
    if not country or not currency:
        country = _field(form, index, "country")
        currency = _field(form, index, "currency").upper()
    raw_subtype = _field(form, index, "raw_card_subtype") or _field(form, index, "subtype")
    brand = _field(form, index, "brand")
    frontend_type = _field(form, index, "frontend_type")
    normalized_subtype = normalize_card_subtype_for_brand(
        brand,
        _field(form, index, "normalized_card_subtype") or raw_subtype,
        frontend_type,
    )
    return {
        "supplier_group": _field(form, index, "supplier_group"),
        "source_text": _field(form, index, "source_text") or _field(form, index, "source_line"),
        "source_line": _field(form, index, "source_line") or _field(form, index, "source_text"),
        "line_no": _to_int(_field(form, index, "line_no")),
        "parse_note": _field(form, index, "parse_note"),
        "brand": brand,
        "country": country,
        "currency": currency,
        "frontend_type": frontend_type,
        "subtype": raw_subtype,
        "raw_card_subtype": raw_subtype,
        "normalized_card_subtype": normalized_subtype,
        "processing_method": _field(form, index, "processing_method") or "fast_card",
        "feedback_note": _field(form, index, "feedback_note"),
        "multiplier": _to_float(_field(form, index, "multiplier")),
        "denom_min": _to_float(_field(form, index, "denom_min")),
        "denom_max": _to_float(_field(form, index, "denom_max")),
        "range_type": _field(form, index, "range_type").lower(),
        "supplier_rate": _to_decimal(_field(form, index, "supplier_rate")),
        "status": _field(form, index, "status") or "active",
        "requirements": _field(form, index, "requirements"),
        "confidence": _to_float(_field(form, index, "confidence"), 0.5) or 0.5,
        "received_at": _field(form, index, "received_at"),
        "expires_at": _field(form, index, "expires_at"),
        "created_by": "",
    }


def _quote_from_payload(supplier_group: str, row: QuoteRowPayload) -> dict[str, Any]:
    source_line = row.source_line.strip() or row.source_text.strip()
    country, currency = split_market_value(row.market)
    if not country or not currency:
        country, currency = row.country.strip(), row.currency.strip().upper()
    raw_subtype = row.raw_card_subtype.strip() or row.subtype.strip()
    brand = row.brand.strip()
    frontend_type = row.frontend_type.strip()
    normalized_subtype = normalize_card_subtype_for_brand(
        brand,
        row.normalized_card_subtype.strip() or raw_subtype,
        frontend_type,
    )
    quote = {
        "supplier_group": supplier_group,
        "source_text": row.source_text.strip() or source_line,
        "source_line": source_line,
        "line_no": row.line_no,
        "parse_note": row.parse_note.strip(),
        "brand": brand,
        "country": country,
        "currency": currency,
        "frontend_type": frontend_type,
        "subtype": raw_subtype,
        "raw_card_subtype": raw_subtype,
        "normalized_card_subtype": normalized_subtype,
        "processing_method": row.processing_method.strip() or "fast_card",
        "feedback_note": row.feedback_note.strip(),
        "multiplier": row.multiplier,
        "denom_min": row.denom_min,
        "denom_max": row.denom_max,
        "range_type": row.range_type.strip().lower(),
        "supplier_rate": row.supplier_rate,
        "status": row.status.strip() or "active",
        "requirements": row.requirements.strip(),
        "confidence": row.confidence if row.confidence is not None else 0.5,
        "created_by": "",
    }
    if row.received_at.strip():
        quote["received_at"] = row.received_at.strip()
    if row.expires_at.strip():
        quote["expires_at"] = row.expires_at.strip()
    return quote


def _validated_quotes(
    conn: Any,
    supplier_group: str,
    rows: list[QuoteRowPayload],
) -> tuple[list[str], list[dict[str, Any]]]:
    errors = []
    quotes = []
    active_brands = {brand["name"] for brand in list_active_brands(conn)}
    active_markets = {market["value"] for market in list_active_markets(conn)}

    if not supplier_group:
        errors.append("请先填写来源群/供应商，再确认保存报价。")

    for index, row in enumerate(rows, start=1):
        if row.deleted:
            continue

        line_label = f"第{row.line_no or index}行"
        row_errors = []
        brand = row.brand.strip()
        country, currency = split_market_value(row.market)
        if not country or not currency:
            country, currency = row.country.strip(), row.currency.strip().upper()
        market_key = market_value(country, currency)

        if not brand:
            row_errors.append("品牌未确认。报价覆盖需要明确 来源群 + 品牌 + 地区/币种，请先手动选择后再保存")
        elif brand not in active_brands:
            row_errors.append(f"品牌不在标准品牌库：{brand}")
        if not market_key:
            row_errors.append("地区/币种未确认。报价覆盖需要明确 来源群 + 品牌 + 地区/币种，请先手动选择后再保存")
        elif market_key not in active_markets:
            row_errors.append(f"地区/币种不在标准库：{country} / {currency}")
        if row.frontend_type.strip() not in {"physical", "code"}:
            row_errors.append("缺少前台类型")
        raw_subtype = row.raw_card_subtype.strip() or row.subtype.strip()
        normalized_subtype = normalize_card_subtype_for_brand(
            brand,
            row.normalized_card_subtype.strip() or raw_subtype,
            row.frontend_type.strip(),
        )
        if not raw_subtype:
            row_errors.append("缺少原始卡细分")
        if normalized_subtype not in normalized_subtype_options_for_brand(brand):
            row_errors.append("统一卡细分待确认")
        range_type = row.range_type.strip().lower()
        if range_type and range_type not in {"bounded", "open", "unlimited", "fixed"}:
            row_errors.append(f"未知面额范围类型：{range_type}")
        if row.denom_min is None and row.denom_max is not None:
            row_errors.append("面额范围不完整，请同时填写上下限、全部留空，或使用“以上/+/>=”表示无上限")
        elif row.denom_min is not None and row.denom_max is None:
            marker_text = " ".join(
                value for value in [row.source_line, row.source_text, row.parse_note] if value
            )
            if not is_open_ended_range(
                row.denom_min,
                row.denom_max,
                marker_text,
                range_type=range_type,
            ):
                row_errors.append("面额范围不完整，请同时填写上下限、全部留空，或使用“以上/+/>=”表示无上限")
        status = row.status.strip() or "active"
        if status == "active" and row.supplier_rate is None:
            row_errors.append("缺少供应商报价")

        if row_errors:
            errors.append(f"{line_label}：" + "，".join(row_errors))
            continue

        quotes.append(_quote_from_payload(supplier_group, row))

    return errors, quotes


def _app_category_rows_from_form(form: Any) -> list[dict[str, Any]]:
    row_count = _to_int(form.get("row_count"), 0) or 0
    rows = []
    for index in range(row_count):
        rows.append(
            {
                "line_no": _to_int(form.get(f"line_no_{index}"), index + 1),
                "category_name": str(form.get(f"category_name_{index}", "")).strip(),
                "brand": str(form.get(f"brand_{index}", "")).strip(),
                "market": str(form.get(f"market_{index}", "")).strip(),
                "normalized_subtype": str(form.get(f"normalized_subtype_{index}", "")).strip(),
                "denom_min": str(form.get(f"denom_min_{index}", "")).strip(),
                "denom_max": str(form.get(f"denom_max_{index}", "")).strip(),
                "multiplier": str(form.get(f"multiplier_{index}", "")).strip(),
                "current_app_price": str(form.get(f"current_app_price_{index}", "")).strip(),
                "status": str(form.get(f"status_{index}", "active")).strip(),
                "note": str(form.get(f"note_{index}", "")).strip(),
                "deleted": form.get(f"delete_{index}") == "on",
            }
        )
    return rows


def _standard_options(conn: Any) -> dict[str, Any]:
    return {
        "brand_options": list_active_brands(conn),
        "market_options": list_active_markets(conn),
        "match_subtype_options": MATCH_SUBTYPE_OPTIONS,
        "raw_subtype_options": RAW_CARD_SUBTYPE_OPTIONS,
        "supplier_group_options": list_supplier_groups(conn),
    }


def _should_save_quote(quote: dict[str, Any]) -> bool:
    return bool(
        quote.get("brand")
        or quote.get("country")
        or quote.get("currency")
        or quote.get("supplier_rate") is not None
        or quote.get("denom_min") is not None
    )


async def _read_large_form(request: Request):
    try:
        return await request.form(max_fields=20000)
    except TypeError:
        return await request.form()


def _field(form: Any, index: int, name: str) -> str:
    return str(form.get(f"{name}_{index}", "")).strip()


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    return to_decimal(value, default)


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def format_number(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return decimal_text(value, str(value))
