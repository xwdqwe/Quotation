# cardsabi-quote-engine

Cardsabi 报价引擎 MVP。第一版只做内部网页工具，不监听微信、不做 OCR、不自动更新 Cardsabi 后台、不调用 Cardsabi API。

## 功能范围

- 群报价解析：客服粘贴微信群报价，系统用规则解析为可编辑表格。
- 报价保存：人工校正后保存到 SQLite 报价库。
- 大段导入：支持一次粘贴长段微信群报价，解析结果保存使用 JSON 批量提交，不受普通表单字段数量限制。
- 标准品牌库/别名库：解析时用品牌别名归一到标准品牌，页面用下拉选择，减少手输脏数据。
- 标准地区/币种库：页面用一个「地区/币种」下拉，保存时拆成 `country` 和 `currency`。
- 散卡/整卡倍数规则：散卡表示 5 倍数，整卡表示 50 倍数，不作为内部细分保存。
- APP 建议报价：按 `品牌 + 国家 + 币种 + 前台类型 + 统一细分 + 倍数 + 面额范围` 聚合，使用 active、未过期且供应群正常的报价，取当前最高可用出货价生成待处理建议。
- 用户卡出货匹配：按卡属性匹配当前供应商报价，输出 Top 3 推荐出货群。
- 供应商报价库：按品牌、国家、类型、细分、处理方式、来源群、状态筛选查看。
- 清空测试数据：本地 MVP 调试时可清空报价、APP 建议价和匹配日志。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 初始化数据库

```powershell
python scripts\init_db.py
```

脚本会创建 `cardsabi.sqlite3`，并写入一组示例报价。

## 清空测试数据

报价库页面提供「清空测试数据」按钮，点击后会二次确认，并清空以下表：

- `supplier_quotes`
- `app_price_records`
- `app_price_suggestions`
- `shipment_match_logs`

这个功能只用于本地 MVP 测试，不删除表结构，也不会调用 Cardsabi 后台。清空后 APP 建议报价会变为空；如需重新写入示例数据，可再次运行 `python scripts\init_db.py`。

## 标准库

系统启动或初始化数据库时，会自动维护三张标准表：

- `card_brands`：标准品牌名，例如 Apple、Razer、Xbox、Steam、Roblox、PSN、Google Play、Amazon、Paysafecard。
- `brand_aliases`：品牌别名，例如 `itunes`、`苹果卡` 会归一为 Apple，`绿蛇`、`欧蛇` 会归一为 Razer，`美亚` 会归一为 Amazon。
- `card_markets`：标准地区/币种，例如 `US / USD`、`Saudi Arabia / SAR`、`New Zealand / NZD`。

新增品牌或别名时，可以在 `app/standards.py` 的 `BRAND_SEEDS` 中补充；新增地区/币种时，在 `MARKET_SEEDS` 中补充。下次启动或运行 `python scripts\init_db.py` 后会同步写入 SQLite。

## 解析规则补充

- `USD散卡`、`CAD整卡`、`AUD散卡`、`GBP整卡`、`EUR散卡` 这类币种和描述粘在一起的写法，会先识别币种对应的地区/币种。
- `散卡` 自动标记 `multiplier=5`，`整卡` 自动标记 `multiplier=50`；如果文本里同时写了明确倍数，以明确倍数为准。`散卡` 遇到 `50倍`、`整卡` 遇到 `5倍` 会在解析备注里提示冲突。
- `横白卡图` 会拆成 `横卡` 和 `白卡` 两条；`横竖卡图` 会拆成 `横卡` 和 `竖卡`；普通 `卡图` 才保存为 `卡图`。
- `极速快刷 50倍数 1-5min`、`快刷网单` 这类没有明确报价的说明行只更新上下文，不生成报价；后续报价会继承对应的处理方式、倍数和反馈时间。
- 反馈时间会单独保存到 `feedback_note`：`极速快刷` 显示为 `极速快刷，约1-5分钟`，`快刷网单` 显示为 `快刷网单，约10-15分钟`，普通 `快刷/快网` 显示为 `快刷，约5-20分钟`。
- `/quotes` 页面支持顶部默认值：默认品牌、默认地区/币种、默认处理方式、默认倍数。默认值只填补解析为空的字段，不覆盖行内明确识别到的内容。
- 默认报价有效期为 24 小时；客服可以在解析前改成 6 小时或其他时长，保存时按页面填写值计算 `expires_at`。
- 来源群/供应商在解析时可以留空，方便先测试解析结果；确认保存报价时仍为必填。
- `代码50=5.25`、`代码:50=5.25`、`代码：50=5.25`、`代码 50=5.25` 都会识别为 `code / 代码/卡密`。
- `香港HK 0.75（500-1500 包50H）只要稳卡`、`美区US 5.35（15-100）` 这类无等号报价，会在同时识别到标准市场、括号前报价和括号内范围时生成报价。
- 无等号报价的括号内非范围内容和括号外说明会写入限制条件，例如 `包50H；只要稳卡`。
- `100/150`、`200/300/400/500` 会按固定面值列表拆成多条单张报价；只有 `100-500`、`100~500` 这类写法才按范围解析。
- `横白` 和 `卡图` 中间夹着 `散卡`、`整卡` 等描述时，仍会拆成 `横卡` 和 `白卡`，不会额外生成普通 `卡图`。
- 出货匹配页输入面额时，如果面额能被 50 整除，会默认建议 `multiplier=50`；如果能被 5 整除但不能被 50 整除，会默认建议 `multiplier=5`，客服仍可手动修改。

## 启动

```powershell
python -m uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

## 公网登录保护

本地开发默认不启用登录。部署到公网服务器时，先生成管理员账号和随机密码：

```bash
python scripts/create_admin_credentials.py --username cardsabi
```

脚本会输出一次性明文密码、密码哈希和会话密钥。把输出的环境变量保存到服务器的 systemd `EnvironmentFile`，不要把明文密码或环境变量文件提交到代码仓库。启动服务前必须设置：

```text
CARDSABI_AUTH_ENABLED=1
CARDSABI_ADMIN_USERNAME=cardsabi
CARDSABI_ADMIN_PASSWORD_HASH=脚本生成的哈希
CARDSABI_SESSION_SECRET=脚本生成的随机密钥
CARDSABI_COOKIE_SECURE=0
CARDSABI_SESSION_HOURS=12
```

没有域名、直接通过服务器 IP 使用 HTTP 时，`CARDSABI_COOKIE_SECURE=0`。这可以阻止陌生人直接操作系统，但 HTTP 不加密账号、密码和报价内容；条件允许时仍建议使用 HTTPS。启用 HTTPS 后把 `CARDSABI_COOKIE_SECURE` 改为 `1`。

## 1核1GB服务器部署

当前项目可以部署到 Ubuntu 24.04、1 vCPU、1GB 内存、25GB SSD 的服务器。生产环境使用 Nginx 监听服务器公网 IP，Uvicorn 仅监听 `127.0.0.1:8000`，并固定为单 worker。部署模板位于：

- `deploy/cardsabi-quote-engine.service`
- `deploy/nginx.conf`

服务器需要安装 `python3-venv`、`nginx` 和 `sqlite3`。应用目录使用 `/opt/cardsabi-quote-engine`，认证环境变量保存到 `/etc/cardsabi-quote-engine.env`，该文件权限应设置为 `600`，不能提交到 GitHub。

1GB 内存服务器建议额外配置 1GB Swap。防火墙只向公网开放 HTTP `80` 和管理员使用的 SSH `22`；Uvicorn 的 `8000` 端口不要向公网开放。

## 回归测试

解析器关键样本回归测试：

```powershell
python scripts\test_parser_cases.py
python scripts\test_quotes_parse_route.py
python scripts\test_quote_workflows.py
```

当前测试覆盖极速快刷上下文、代码固定面值、`[US横白】` 混合括号、固定面值列表拆分、地区报价、两行组合报价、后置备注回填、`#` 注释行和随机字符串忽略。

`test_quotes_parse_route.py` 覆盖 `/quotes/parse` 页面表单链路，并验证“地区/币种 + 报价 + 括号面额范围”样本生成 6 条报价。

`test_quote_workflows.py` 覆盖卡细分归一化、前三名报价、供应群暂停/待刷新/恢复、批次撤回、一键确认筛选、新报价软覆盖旧报价、供应商报价库默认隐藏历史报价、APP 后台建议价确认和操作日志。

## 报价批次与供应群状态

- 每次确认保存会生成 `quote_batch_id`，格式为 `QBYYYYMMDD_序号`。
- 撤回批次使用 `revoked` 软状态，不删除报价历史。
- 供应群状态流为 `normal -> paused -> needs_refresh -> normal`。
- `needs_refresh` 群必须存在进入待刷新之后的新确认报价，才允许恢复 `normal`。
- 出货匹配只使用 `status=active`、未过期且供应群为 `normal` 的报价。
- 同一匹配 key 每个供应群只取最新有效报价，再按供应商报价降序生成激进价、建议价、安全价。

## 数据库迁移

启动应用或运行下面命令会自动执行兼容迁移，不会硬删除旧报价：

```powershell
python scripts\init_db.py
```

主要新增字段：

- `supplier_quotes.raw_card_subtype`
- `supplier_quotes.normalized_card_subtype`
- `supplier_quotes.quote_batch_id`
- `supplier_quotes.supplier_group_id`
- `supplier_quotes.confirmed_at`

主要新增表：

- `supplier_groups`
- `quote_batches`
- `operation_logs`

## 示例使用流程

1. 进入「群报价解析 / APP建议报价」。
2. 来源群填写 `测试群`。
3. 粘贴示例报价：

```text
Apple US 横卡 50-500 5.20 快卡
苹果 美区 白卡 50-500 5.00 快卡
Apple US 纯代码 50-500 5.40 快刷
Amazon UK 实体卡 25-300 0.91 快卡 发前问
Steam EUR 代码 10-200 0.88 慢刷
```

4. 点击「解析报价」，在表格里校正识别结果。
5. 点击「确认保存报价」。页面会先显示覆盖预览，确认后把当前可见且未勾选删除的解析行组装为 JSON 批量提交，可处理大段群报价和 500 条以上解析记录。
6. 页面下方查看 APP 后台建议报价。建议清单会持久保存，刷新或切换页面后仍显示所有未处理项；客服确认已在 APP 管理后台同步后，点击「已同步到管理后台」。如果当前没有可用报价且需要把后台价填 0，点击「已在管理后台填0」。
7. 进入「用户卡出货匹配」，使用标准下拉字段填写卡属性，例如：

```text
品牌：Apple
地区/币种：US / USD
前台类型：physical
人工细分：白卡
面额：100
倍数：50
处理方式：不限
```

8. 点击「查询匹配」，系统会返回 Top 3 推荐出货群；如果没有完全匹配，会展示相近报价并标记仅供参考。

### 新报价覆盖旧报价

同一来源群、品牌、地区/币种保存新报价时，旧报价会被软覆盖为 `superseded / 已覆盖`，历史记录保留但不再参与出货匹配和 APP 后台建议报价。供应商报价库默认只显示当前有效报价；需要排查历史时，将「包含历史报价」切换为「是」。

## 目录结构

```text
app/
  main.py              FastAPI 路由和页面入口
  database.py          SQLite 建表、连接、示例数据
  standards.py         标准品牌、别名、地区/币种配置
  parsing.py           群报价解析和字段标准化
  pricing.py           APP 建议报价计算
  matching.py          用户卡出货匹配
  templates/           Jinja2 页面模板
  static/styles.css    基础样式
scripts/
  init_db.py           数据库初始化脚本
SPEC.md                产品需求说明
requirements.txt       Python 依赖
```

## MVP 说明

- 解析逻辑基于规则和正则，不依赖外部 AI API。
- 无法高置信度识别的行会保留原文，并降低置信度，客服可在保存前人工修改。
- 来源群/供应商在保存时必须填写；保存时前端和后端都会校验，避免报价无法追溯。
- 品牌、地区/币种、前台类型、内部细分使用标准下拉字段，出货匹配页面也使用同一套标准字段。
- APP 建议报价不会写入 Cardsabi 后台；系统只在 `app_price_suggestions` 中维护待处理建议，并在客服点击确认后写入本地 `confirmed_app_prices` 作为后续对比基准。
- `/quotes` 页面下方的 APP 建议报价只基于已保存的报价库，不包含尚未保存的解析结果。
- 慢刷报价默认不参与 APP 后台建议价，只参与用户卡出货匹配。
