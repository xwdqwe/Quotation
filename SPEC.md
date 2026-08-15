# Cardsabi Quote Engine - Codex Task

项目名：cardsabi-quote-engine  
中文名：Cardsabi 报价引擎

## 业务背景

Cardsabi 是礼品卡回收 APP。我们和多个礼品卡需求方通过微信群对接，对方会发布礼品卡报价。客服现在需要人工从大量群消息里筛选最高报价，再人工填写 Cardsabi 管理后台；用户上传礼品卡后，客服还要翻群找哪个群报价最高。

第一版只做内部工具，不接 Cardsabi 后台，不自动更新后台，不监听微信，不做 OCR。

## 技术要求

使用 Python + FastAPI + SQLite + Jinja2/HTMX 或简单模板实现。  
优先保证可运行、易维护、流程清晰。  
不要复杂前后端分离。  
需要 README、数据库初始化脚本、基础 CSS、示例数据。

首页只有两个入口：

1. 群报价解析 / APP建议报价
2. 用户卡出货匹配

另加一个辅助页面：供应商报价库查看。

---

## 一、核心板块

### 板块 1：群报价解析 / APP建议报价

客服从微信群复制报价文本，粘贴到系统 textarea，选择来源群，点击解析。

系统解析后不要直接保存，先显示可编辑解析表。客服可以修改、删除错误行，然后点击“确认保存报价”。

保存后，系统重新计算 APP 后台建议报价。

Cardsabi 后台只能填写粗粒度字段：

- 品牌
- 国家/币种
- 物理卡/代码
- 倍数
- 面额范围
- 报价
- 折扣
- 状态

Cardsabi 后台不能填写：

- 横卡、竖卡、白卡、电子图等内部细分
- 快卡、快刷、慢刷等处理方式

所以 APP 后台建议报价只能按粗粒度输出：

brand + country + currency + frontend_type + multiplier + denom_min + denom_max

默认只显示需要客服去后台处理的报价。无变化默认隐藏，但要有 tab 可以查看。

### 板块 2：用户卡出货匹配

用户上传礼品卡后，客服在 Cardsabi 管理后台看图，人工判断卡属性和细分，然后来到本系统填写：

- 订单号/交易号，可选
- 品牌
- 国家/币种
- 前台类型：physical/code
- 人工细分 subtype
- 面额 amount
- 倍数 multiplier
- 处理方式筛选：不限 / 快卡 / 快刷 / 慢刷

系统从供应商报价库中匹配当前可用报价，输出 Top 3 推荐出货群。

---

## 二、数据库表

### supplier_quotes

字段：

- id
- supplier_group：来源群/供应商名称
- source_text：原始微信群报价文本
- brand：Apple、Steam、Google Play、Xbox、Amazon、Roblox、PSN 等
- country：US、UK、Germany、Hong Kong、Canada 等
- currency：USD、GBP、EUR、HKD、CAD 等
- frontend_type：physical 或 code
- subtype：横卡、竖卡、白卡、普通物理卡、纯代码、电子图、待确认
- processing_method：fast_card、fast_process、slow_process
- multiplier：5、50、100；无法识别可为空
- denom_min
- denom_max
- supplier_rate
- status：active / ask_first / paused / unavailable / warning
- requirements：限制条件/备注
- confidence：0-1
- received_at
- expires_at：默认 received_at + 6 小时
- created_by，可为空
- created_at
- updated_at

### app_price_records

字段：

- id
- brand
- country
- currency
- frontend_type：physical/code
- multiplier
- denom_min
- denom_max
- suggested_backend_rate：本次建议后台报价
- recorded_backend_rate：系统记录价，代表上次客服确认已填写到 Cardsabi 后台的价格
- change_amount：本次建议价 - 系统记录价
- status：need_update / no_change / new / suggest_pause / risk_changed / abnormal_review / initial_confirm
- reason：建议原因
- last_confirmed_at
- created_at
- updated_at

### shipment_match_logs

可选但建议加：

- id
- order_no
- brand
- country
- currency
- frontend_type
- subtype
- amount
- multiplier
- selected_quote_id
- created_at

---

## 三、字段标准化规则

### 品牌映射

- Apple、苹果、iTunes、ITUNE -> Apple
- Steam、蒸汽 -> Steam
- Google Play、谷歌、GP -> Google Play
- Xbox、XBOX -> Xbox
- Amazon、亚马逊 -> Amazon
- Roblox、ROBLOX -> Roblox
- PSN、PlayStation -> PSN

### 国家/币种映射

- US、USA、美国、美区、USD -> country=US, currency=USD
- UK、英国、英区、GBP -> country=UK, currency=GBP
- EUR、欧元、欧洲、德国、法国、荷兰等 -> currency=EUR，country 尽量识别，无法识别 country=EU
- HK、香港、HKD -> country=Hong Kong, currency=HKD
- CAD、加拿大、加区 -> country=Canada, currency=CAD
- AUD、澳洲、澳大利亚 -> country=Australia, currency=AUD

### 前台类型 frontend_type

- 横卡、竖卡、白卡、实体卡、物理卡、卡片 -> physical
- 纯代码、代码、电子图 -> code
- 卡图、截图 -> subtype=待确认，confidence 降低，不要强行归类

### 内部细分 subtype

- 横卡 -> 横卡
- 竖卡 -> 竖卡
- 白卡 -> 白卡
- 实体卡/物理卡 -> 普通物理卡
- 代码/纯代码 -> 纯代码
- 电子图 -> 电子图
- 卡图/截图 -> 待确认

### 处理方式 processing_method

标准值只保留三类：

- 快卡、快加 -> fast_card
- 快刷、快网 -> fast_process
- 慢刷、慢网 -> slow_process
- 未说明 -> fast_card

### 状态 status

- 包含“暂停”“停收”“暂不收” -> paused
- 包含“不收”“不要”“拒收”“不接” -> unavailable
- 包含“问”“发前问”“提前问” -> ask_first
- 包含“锁卡”“拒付”“不结算” -> warning
- 正常报价 -> active

### 有效期

- 默认有效期 6 小时
- 文本出现“30分钟”“半小时” -> 30 分钟
- 出现“发前问” -> status=ask_first，不参与 APP 建议报价，只作为出货匹配候选提醒

---

## 四、APP 后台建议报价计算规则

1. 只使用 status=active 的报价。
2. 默认只参考 processing_method=fast_card 和 fast_process。
3. slow_process 默认不参与 APP 后台建议报价，只用于板块 2 出货匹配。
4. 物理卡建议价不能取最高特殊细分价，要取保守可成交价。
   - 例如 Apple US 物理卡：横卡 5.20、竖卡 5.10、白卡 5.00，则 APP 物理卡建议价应接近 5.00，而不是 5.20。
5. 代码建议价也要保守。
   - 例如 Apple US 代码：电子图 5.65、纯代码 5.40，则 APP 代码建议价应按 5.40，而不是 5.65。
6. 没有 active 报价 -> suggest_pause。
7. 本次建议价相比 recorded_backend_rate 变化超过 10% -> abnormal_review。
8. 本次建议价 = recorded_backend_rate -> no_change，默认隐藏。
9. 本次建议价 != recorded_backend_rate -> need_update。
10. 没有历史 recorded_backend_rate -> initial_confirm。

APP建议报价操作：

- 已更新：客服已去 Cardsabi 后台人工填写本次建议价，点击后 recorded_backend_rate = suggested_backend_rate，状态变 no_change。
- 确认一致：第一次初始化时，客服核对后台已是这个价格，点击后 recorded_backend_rate = suggested_backend_rate。
- 暂不处理：保留状态，可记录备注。

不要要求客服手动输入上次后台价。系统自己维护 recorded_backend_rate。

---

## 五、板块 2 匹配逻辑

匹配条件：

- brand 一致
- country/currency 一致
- frontend_type 一致
- subtype 一致
- multiplier 一致；用户未填 multiplier 时忽略 multiplier
- amount 在 denom_min 和 denom_max 范围内
- status=active 优先
- 未过期报价优先
- 如果选择处理方式，则只匹配该处理方式；如果选择“不限”，fast_card / fast_process / slow_process 都可以候选

排序规则：

1. supplier_rate 高的优先
2. 同报价时，fast_card 优先于 fast_process，fast_process 优先于 slow_process
3. 同报价同处理方式时，received_at 最新优先

输出 Top 3：

- 排名
- 来源群/供应商
- 供应商报价
- 处理方式中文：快卡/快刷/慢刷
- 预计反馈：快卡约 1-2 分钟；快刷约 5-20 分钟；慢刷显示慢反馈
- 范围
- 状态
- 限制条件
- 原始报价文本
- 报价录入时间
- 过期时间

没有完全匹配时：
显示“没有完全匹配报价”，同时给出同品牌/国家/类型的相近报价，并明确标记“仅供参考，不能直接使用”。

---

## 六、页面要求

### 首页

标题：Cardsabi 报价引擎

两个大按钮：

1. 群报价解析 / APP建议报价
2. 用户卡出货匹配

### 板块 1 页面

包括：

- 来源群/供应商输入
- 默认有效期
- 微信群报价 textarea
- 解析按钮
- 解析结果可编辑表格
- 确认保存报价按钮
- APP 后台建议报价更新清单
- 状态 tab：需要处理 / 无变化 / 全部

解析结果表列：

- 品牌
- 国家
- 币种
- 前台类型
- 内部细分
- 处理方式
- 倍数
- 面额范围
- 供应商报价
- 状态
- 限制条件
- 来源群
- 置信度
- 操作

APP建议报价表列：

- 状态
- 品牌
- 国家
- 币种
- 前台类型
- 倍数
- 范围
- 系统记录价
- 本次建议价
- 变化
- 原因
- 操作

### 板块 2 页面

包括：

- 用户卡属性输入表单
- 查询按钮
- Top 3 出货推荐结果
- 相近报价提示

### 供应商报价库页面

支持按：

- 品牌
- 国家
- 类型
- 细分
- 处理方式
- 来源群
- 状态

筛选查看。

---

## 七、解析要求

第一版不要求 100% 解析复杂群报价，但要做到：

- 能解析常见行格式
- 无法识别的行保留原文，标记 confidence 低
- 解析结果允许客服人工修改
- 不要因为解析失败而丢弃原始文本
- 先用规则/正则实现，不依赖外部 AI API
- 后续方便添加真实群报价样本和规则

---

## 八、交付要求

请完成：

1. 项目结构
2. FastAPI 应用
3. SQLite 数据库模型
4. 数据库初始化脚本
5. 两个主页面
6. 供应商报价库查看页面
7. 报价解析基础逻辑
8. APP 建议报价计算逻辑
9. 用户卡出货匹配逻辑
10. README.md，包含安装和启动方式
11. 示例数据和示例使用流程

先实现可运行 MVP，不要追求完美。重点是业务流程跑通。
