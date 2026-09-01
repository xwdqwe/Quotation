# cardsabi-quote-engine

Cardsabi 内部报价解析器。系统只负责：

1. 粘贴微信群报价。
2. 解析并人工校正标准字段。
3. 校验一个商家、一个品牌的完整报价批次。
4. 发送到 Cardsabi 管理后台。

出货匹配、报价保存、APP 建议价、暂停或恢复报价均由 Cardsabi 管理后台负责，本项目不再维护这些业务。

## 当前边界

- 不监听微信，不做 OCR。
- 不在本地保存供应商报价库。
- 不做用户卡出货匹配。
- 不计算 APP 后台建议报价。
- 不根据“暂停/不可用”文本自动关闭 Cardsabi 报价。
- 每次发送只允许一个 Cardsabi 商家和一个标准品牌。
- 发送成功后，Cardsabi 按“商家 + 品牌”全量替换；该商家的其他品牌不受影响。
- Cardsabi 任意一条校验失败时整批回滚，本地只记录失败结果。

## 字段转换

- 卡类型（`cardType`）：`Physical`、`Code`、`ECode`，三者是不同报价，不相互覆盖。
- 报价页会动态刷新 Cardsabi 商家、品牌和国家目录；正式发送前会强制再次刷新并校验。实时目录不可用时整批停止发送，不会继续使用旧缓存。
- 当前开放接口没有卡类型目录查询接口，`cardType` 按接口契约固定校验为 `Physical`、`Code`、`ECode`。
- 卡头（`bin`）：有值时发送，并参与 Cardsabi 同报价条件判断。
- 卡速（`cardSpeed`）：在“接口设置”按品牌配置 `Fast` 或 `Slow`，不从快卡、快刷、慢刷推断。
- 商家备注（`merchantRemark`）：包含处理方式、反馈时间、状态和对接群备注；无内容时发送 `-`；最多 1000 字符。
- 国家（`country`）：解析页面显示地区/币种，发送时只提交 Cardsabi 国家简称。
- 报价（`price`）：以字符串发送，最多 15 位小数，避免小数精度丢失。
- 范围不限：转换为 `10-100000`；有倍数时，下限会调整为第一个合法倍数。
- `200以上`：转换为 `200-100000`。
- 固定面值：`minimum == maximum`。
- 倍数范围：上下限必须能被 `multipleValue` 整除，且下限不能小于倍数。

同一个 Cardsabi 报价条件下，如果横卡、白卡等多个原始物理细分价格不同，系统取较低价格发送，并在 `merchantRemark` 写明各原始细分价格。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\init_db.py
```

## 接口配置

测试环境默认地址：

```text
http://18.232.59.40:8001/cardsabi
```

通过环境变量配置：

```text
CARDSABI_API_BASE_URL=http://18.232.59.40:8001/cardsabi
CARDSABI_API_USERNAME=测试接口账号
CARDSABI_API_PASSWORD=测试接口密码
CARDSABI_API_TIMEOUT_SECONDS=30
```

账号和密码不得提交到 GitHub。配置后进入“接口设置”，依次：

1. 同步 Cardsabi 商家、品牌和国家。
2. 将解析品牌映射到 Cardsabi `categoryName`。
3. 为每个会发送的品牌设置 `cardSpeed=Fast/Slow`。
4. 核对解析地区到 Cardsabi 国家简称的映射。

## 使用流程

1. 进入 `/quotes`。
2. 选择 Cardsabi 商家。解析前可以暂不选择，发送前必须选择。
3. 粘贴一种品牌的完整报价并解析。
4. 校正品牌、地区、卡类型、原始细分、面额、倍数、价格、处理方式、BIN 和备注。
5. 点击“发送到 Cardsabi”。
6. 系统再次校验单品牌、目录映射、面额和备注长度。
7. 二次确认后整批发送；成功或失败记录可在 `/history` 查看。

暂停或不可用报价不会发送，页面会提示客服到 Cardsabi 后台人工关闭。发前问和风险状态仍可发送，并写入商家备注。

## 目录与历史数据

SQLite 只用于：

- 标准品牌、别名和地区解析库。
- Cardsabi 商家、品牌和国家目录缓存。
- 品牌卡速与国家简称映射。
- 最近 7 天的发送成功/失败记录。

旧版本的报价、匹配和建议价表不会在迁移时物理删除，但新页面和新发送流程不再读取这些表。

## 启动

```powershell
python -m uvicorn app.main:app --reload
```

本机打开：`http://127.0.0.1:8000`。

## 公网登录保护

生成管理员账号和随机密码：

```powershell
python scripts\create_admin_credentials.py --username cardsabi
```

将输出保存到服务器 `/etc/cardsabi-quote-engine.env`，权限设为 `600`：

```text
CARDSABI_AUTH_ENABLED=1
CARDSABI_ADMIN_USERNAME=cardsabi
CARDSABI_ADMIN_PASSWORD_HASH=生成的哈希
CARDSABI_SESSION_SECRET=生成的随机密钥
CARDSABI_COOKIE_SECURE=0
CARDSABI_SESSION_HOURS=12
```

无域名且仍使用 HTTP 时只能设置 `CARDSABI_COOKIE_SECURE=0`，账号、密码和报价内容不会被传输加密。正式环境应切换 HTTPS 后设置为 `1`。

## 服务器

Ubuntu 24.04、1 vCPU、1GB 内存、25GB SSD/NVMe 足够当前内部使用。建议配置 1GB Swap。部署模板：

- `deploy/cardsabi-quote-engine.service`
- `deploy/nginx.conf`

Uvicorn 只监听 `127.0.0.1:8000`，Nginx 对外提供入口，防火墙仅开放 SSH 和网页端口。

## 生产上线阻断项

在切换正式 Cardsabi 接口前，必须再次确认并完成：

1. 使用 HTTPS，不允许生产报价和凭据走明文 HTTP。
2. 使用服务端接口密钥或签名认证，不继续使用网页账号密码作为长期生产认证。
3. 让 Cardsabi 将报价解析服务器公网 IP `167.179.69.149` 加入接口白名单。
4. 用一个测试商家、一个测试品牌执行真实 POST，并确认“商家 + 品牌”全量替换和整批回滚结果。

## 回归测试

```powershell
python scripts\test_parser_cases.py
python scripts\test_quotes_parse_route.py
python scripts\test_cardsabi_sync.py
python scripts\test_auth.py
```

- `test_parser_cases.py`：保留微信群复杂报价的解析回归。
- `test_quotes_parse_route.py`：验证 `/quotes/parse` 页面链路。
- `test_cardsabi_sync.py`：验证单品牌限制、卡类型、国家映射、范围转换、价格合并、小数精度、备注长度和 7 天历史清理。
- `test_auth.py`：验证公网登录会话。

## 主要目录

```text
app/
  main.py               FastAPI 页面和发送入口
  parsing.py            微信群报价解析器
  cardsabi_client.py     Cardsabi 开放接口客户端
  quote_sync.py         发送前校验、转换和合并
  sync_store.py         目录映射与 7 天发送记录
  database.py           SQLite 与解析标准库兼容层
  templates/            报价、设置、历史页面
scripts/
  init_db.py
  test_parser_cases.py
  test_quotes_parse_route.py
  test_cardsabi_sync.py
```
