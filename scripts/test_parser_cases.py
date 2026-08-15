from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.parsing import classify_numbers_in_line, parse_quote_line, parse_quote_text  # noqa: E402


FAST_PROCESS_FIXED_VALUE_SAMPLE = """单独更新 ===== =====
极速快刷 50倍数 1-5min-
代码:50=5.25(单张)
代码:100/200=5.42(单张)
[US横白】卡图50=【5.55】（50倍数）
[US横白】卡图100/150=【5.62】（50倍数）
[US横白】卡图350/450=【5.72】（50倍数）
[US横白】卡图200/300/400/500=【5.72】（50倍数）
#us拒竖卡------us拒竖卡
#赎回多扫卡多P图停止合作
#卡图需完整带背景
#网单无后台 #下不过退
#默认包40min#扫卡/赎回减账单
)w0%pR
"""

MARKET_RATE_RANGE_SAMPLE = """苹果卡：卡图
香港HK 0.75 （500-1500 包50H）只要稳卡
香港HK 0.75 （1501-3000 包50h）只要稳卡
香港HK 0.75 （3001-5000 包50h）只要稳卡
香港HK 0.715（150-490 包6H）只要稳卡
香港批量卡问~
美区US 5.35（15-100）
加拿大CAD 3.7（15-100）
"""

TWO_LINE_SAME_RATE_SAMPLE = """单独更新其他价格不变
===================
💰瑞典：图/密同价：0.475
💰面值：200~5000：100倍数
💰挪威：图/密同价：0.475
💰面值：200~5000：50倍数
💰备注：以上200面值以下不加账
💰要求：来稳的老客户卡
"""

RAZER_UNBOUNDED_SAMPLE = """==== 雷蛇 Razer ====
美 USD =5.63 ↑↑
新 SGD =4.18
澳 AUD =3.90
加 CAD =4.00
墨 MXN=0.323
欧 EUR= 5.10 [RG10+]
英 UK = 5.10 [RG10+]
【问】其他国家/代码批量（5张+）
"""

ITUNES_ELECTRONIC_SAMPLE = """【iTune-US  1-8分钟左右快刷】
US-电子：10-190=5.15（5倍）
US-电子：100-500=5.50（50倍）
"""

ITUNES_FULL_SAMPLE = """=======【iTune-US  1-8分钟左右快刷】=====
US-横白：10-90=5.45                 完整清晰卡图挑图
US-横白：100/150=5.8               完整清晰卡图挑图
US-横白：200/350/450=5.83       完整清晰卡图挑图
US-横白：300/400/500=5.83        完整清晰卡图挑图
=============================
US-电子：10-190=5.15        （5倍）
=============================
US-电子：100-500=5.50      （50倍）
===========================
US-竖卡：100-500=5.45     （50倍）
"""

CARD_SECRET_SAME_CONTEXT_SAMPLE = """====挪威瑞典卡密同快加===
挪威 100-4000=0.47  50倍数
瑞典 100-4000=0.46  50倍数
"""

OPEN_ENDED_RANGE_SAMPLE = """====南非====
200以上图/密=0.265
"""

HASH_BRACKET_APPLE_SAMPLE = """---------价格更新-------------
#US      卡图快加【5.21】10-200（5倍数）囤卡，稳发
#US      电子代码快加【5.16】10-200（5倍数）囤卡，稳发
#US      卡密快加【5.11】面值15-90（5倍数）
#压90分钟 100us
#卡图电子最多要2连
 #ITS不要 #ITS不要 #ITS不要
------------itunes---------------
#CAD     图密【3.55】面值    10-300（5 倍数）
#UK    图密【5.8】面值    10-200（5倍数）
#瑞士   图密【6.0】面值    10-200（5倍数）
#aud   图密【3.3】面值   10-300（5倍数）
------------日本--------------
#日本 图密【0.033】面值    5000-10W（1000倍数）
#包50小时再发
======苹果欧盟汇率======
#德国   图密【4.7】面值10-200（5倍数）
#比爱奥   图密【4.7】面值10-200（5倍数）
------------------------------------
更新价格期间漏卡麻烦提醒一下
#备注:所有苹果卡任何国家默认多发卡不接受争议哪边加账算哪边
超过1分钟没回直接转，省的纠纷!!!!
#30分钟内赎回双禁不结账
"""

RAZER_MULTI_MARKET_SAMPLE = """==== 雷蛇 Razer ====
欧盟/英国 =5.3RG（问） 马来西亚=1.44
巴西       =1.07         墨西哥  =0.325
新加坡     =4.26      菲律宾 =0.095
加拿大     =3.98        澳元=3.90
泰国       =0.16             哥伦比亚=0.001
印尼雷蛇   =0.00033       土耳其=0.12
印度   =0.055                   新西兰=3.20
日本雷蛇=0.03问              智利=0.001
"""

PRECISION_SAMPLE = """==== 雷蛇 Razer ====
印尼雷蛇=0.00033
印度尼西亚-IDR----【0.00018】
哥伦比亚=0.0011
"""

XBOX_MULTI_MARKET_SAMPLE = """#【Xbox】 【5倍图密】（批量问）
US 10-250=5.26卡密同价
UK10-250=5.95卡密同价
EUR=5.1卡图  代码5.05
巴西=0.82        新加坡=3.25
加拿大=3.3         新西兰=2.75
AUD=3.1       瑞典=0.44
挪威=0.44          韩国=0.0037
瑞 士=5.1      哥伦比亚=0.0011
丹麦=0.57           墨西哥=0.27
波兰=1.1             捷克=0.15
以色列=1.1            香港=0.55
南非=0.15         迪拜阿联酋=0.7
台湾=0.07            沙特阿拉伯=1.2
匈牙利=0.009         日 本  =0.031（问）
印度=0.03               智利=0.002
"""

XBOX_DEFAULT_SAME_RATE_SAMPLE = """XBOX
us 10-250=5.20（5倍）
"""

APPLE_HORIZONTAL_WHITE_SAMPLE = """=====us极速快刷1-5min======
US横白:50=5.53 （单张）
US横白:100/150=5.68
US横白:200-500=5.7 (100倍）
"""

ROBLOX_MATRIX_SAMPLE = """〖 Roblox〗
USD=3.5欧盟 EUR 3.5 UK=3.8
cad 2.2  aud 1.9 泰国0.1  墨西哥 0.16
马来西亚   0.6  新西兰 1.7   巴西0.5
新加坡2.2  瑞典/挪威 0.25 其他国家问
（RA开头游戏币不要）
"""

PSN_MATRIX_SAMPLE = """〖 psn  PlayStation〗批量提前问
US=3.95 (10-200)  100以上问
UK=4.2（5-200）
EUR=3.45（5-200） 200以上2.8
（葡萄牙  斯洛伐克 克罗地亚   爱尔兰  法国  德国
西班牙  荷兰   奥地利  比利时  意大利  希腊  芬兰  斯洛文尼亚）
AUD 1.6 （10-300）新西兰 1.5 丹麦 0.2 巴西 0.6 马来西亚0.5
CAD 1.9（10-500）瑞典 0.23 挪威 0.23 台湾 0.06（问）
泰国 0.05 保加利亚 1.9 新加坡 1.7 瑞士 3.0
"""

AMAZON_DUAL_RATE_SAMPLE = """〖Amazon〗卡图  连卡大卡问
美亚  50-200=5.4卡图   代码5.2
美亚  201-500=5.3卡图  代码5.1
英亚  25-200=5.9卡图  代码4.9
德亚  25-200=5.0卡图  代码4.0
加亚  50-200=3.3卡图  代码2.5
意亚  25-200=4.6卡图  代码4.0
澳亚  25-200=3.2卡图  代码2.6
"""

GOOGLE_PLAY_DASHED_SAMPLE = """〖Google play〗 卡图
美国------USD---------【4.4】
（连卡代码提前问.不要直接发）
德国------EUR----------【3.8】
英国------UK-----------【3.7】
瑞士------CHF----------【3.7】
加拿大----CAD---------【2.5】
澳大利亚--AUD---------【2.0】
新西兰----NZD---------【1.8】
波兰-------PLN---------【0.2】
日本-------JPY-------【275】1W等于1*275
沙特-------SAR---------【0.5】
阿拉伯-----AED--------【0.6】
墨西哥-----MX--------【0.11】
南非------ ZAR--------【0.11】
印度-------INR-------【0.032】
印度尼西亚-IDR----【0.00018】
土耳其-----TRY--------【0.05】
香港--------HK--------【0.32】
韩国--------KR------【26】 1W等于1*26
"""

PAYSAFECARD_DEFAULT_SAME_RATE_SAMPLE = """〖Paysafecard 〗(其他国家问）发前问
欧盟 EUR    50-500==6.43
瑞士 CHF    50-500==6.8
英国 GBP    50-500==7.15
希腊 GR      50-500==5.7
葡萄牙       50-500==5.7
挪威K   150-5000==0.55
瑞典/SEK     150-5000==0.56
罗马尼亚/RON   100-1000==1.1
波兰/PLN      50-500==1.35
丹麦/DKK      100-5000==0.7
匈牙利  HUF     5000-50000=0.015发前问
捷克/CZK       300-3000=0.24
澳大利亚/AUD  25-500=3.2
加拿大/CAD    25-500=3.6
"""

LONG_TAIL_MULTI_RANGE_SAMPLE = """Sephora 50-99=4.3 100-500=4.8
Footlocker 50-99=4.4 100-500=5.3
"""

APPLE_LOOSE_EUROPE_SAMPLE = """倍数：10倍数 100+
比/意/奥/ 5.13
芬兰 5.13
"""

APPLE_COMPLEX_BLOCK_SAMPLE = """===iTunes报价=======
💰德国：整卡卡图：5.13
💰面值：50~250 ：50倍数
💰来稳的老客户卡，不稳不要发
===================
💰波兰：卡密同价：1.3
💰倍数：10倍数   100+
💰备注：50以下面值不加账
连卡多发提醒一下，否则赎回减账
===================
💰英国：卡图整卡/散卡：5.88
💰面值：15~200    5倍数
💰来稳的老客户卡，不稳不要发
===================
💰 欧盟：荷兰 /法国/西班牙 5.15
💰 比/意/奥/ 5.13
💰 芬兰 5.13
💰 整卡卡图：  50倍数
===================
💰瑞士：整卡卡图：50~200  6.35
💰瑞士面值：250  6.32
💰来稳的老客户卡，不稳不要发
===================
💰新西兰：整卡卡图：3.1
💰面值：50~500   50倍数
💰来稳的老客户卡，不稳不要发
===================
💰澳大利亚：整卡卡图：3.45
💰面值：50~300：50倍数
💰来稳的老客户卡，不稳不要发
===================
💰日本：1W~5W卡图：0.0355
💰面值：1000倍数
💰面值：6W~10W   0.034
💰来稳的老客户卡，不稳不要发
===================
💰瑞典：图/密同价：0.47
💰面值：200~5000：100倍数
💰挪威：图/密同价：0.475
💰面值：200~5000：50倍数
💰备注：以上200面值以下不加账
💰要求：来稳的老客户卡
"""

APPLE_BRACKETED_COUNTRY_BLOCK_SAMPLE = """【美国】US代码不收 #50#100#150面值不要
卡图10-195=5.4【5倍数】
#Redeem Now不要#纸质发票不要#电子图不要
----------------------------
【加拿大】 #50#100#150面值不要
卡图：10-190=3.7【5倍数】#连卡不超过3张
#只要四角清晰的卡图#带发票的不要
-------------------------------
【德国】
卡图：5-195=5.1#5的倍数
卡图：50-150=5.15(50倍数)#不超过三连
卡图：200=5.15(50倍数)#不超两连
连卡200*3不拿
----------------------------------
【 比利时 爱尔兰 奥地利 意大利 荷兰 芬兰 】
卡图：50-200=5.15(50倍数)#不超过三连
卡图：200=5.15(50倍数)#不超两连
卡图：250=5.1(50倍数)#只要单张
连卡200*3不拿
----------------------------------
【 法国  西班牙 】
卡图：50-200=5.18(50倍数)#不超过三连
卡图：200=5.18(50倍数)#不超两连
卡图：250=5.13（50倍数)#只要单张
连卡200*3不拿
----------------------------------
【AUD】
50-150=3.4图(50倍数)#不超过三连
10/20/30=3.4图#连卡不超过三张张
"""

APPLE_BRACKET_MARKET_SUBTYPE_SAMPLE = """（iTunes美卡）
【USD散卡】10~190=5.4（5倍审图）
#屏幕/模糊/局部电子一律不拿！！！
#沃尔玛电子图一律不要！！后续测出会减账
#电子图请发带时间/网址的完整截图！！！
--------------------

（iTunes外卡）
【CAD散卡】10~500=3.73（5倍）
【CAD整卡】100~500=3.73（50倍快加）
【AUD散卡】20~500=3.35（10倍）
【AUD整卡】100~300=3.4（50倍快加）
#囤卡/不熟悉/不稳/别发！
--------------

（iTunes欧盟）
【德国散卡】10~200=5.1【5倍】连卡问
【德国整卡】100~250=5.1【横白卡图快加】
"""


def rows_for(source_line: str, rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["source_line"] == source_line]


def assert_money(value: object, expected: object) -> None:
    assert value is not None
    assert Decimal(str(value)) == Decimal(str(expected)), value


def test_fast_process_fixed_value_sample() -> None:
    rows = parse_quote_text("回归测试群", FAST_PROCESS_FIXED_VALUE_SAMPLE)

    assert len(rows) == 21, len(rows)
    assert not rows_for("极速快刷 50倍数 1-5min-", rows)
    assert parse_quote_line("回归测试群", "极速快刷 50倍数 1-5min-") == {}
    assert not any(row["source_line"].startswith("#") for row in rows)
    assert parse_quote_line("回归测试群", "#卡图需完整带背景") == {}
    assert parse_quote_line("回归测试群", ")w0%pR") == {}
    assert not rows_for(")w0%pR", rows)
    assert not any(row["source_line"] == "单独更新 ===== =====" for row in rows)

    code_50 = rows_for("代码:50=5.25(单张)", rows)
    assert len(code_50) == 1
    assert code_50[0]["frontend_type"] == "code"
    assert code_50[0]["subtype"] == "代码/卡密"
    assert code_50[0]["denom_min"] == 50
    assert code_50[0]["denom_max"] == 50
    assert_money(code_50[0]["supplier_rate"], 5.25)
    assert code_50[0]["multiplier"] == 50
    assert code_50[0]["processing_method"] == "fast_process"
    assert code_50[0]["feedback_note"] == "极速快刷，约1-5分钟"
    assert "单张固定面值" in code_50[0]["requirements"]

    code_100_200 = rows_for("代码:100/200=5.42(单张)", rows)
    assert len(code_100_200) == 2
    assert sorted((row["denom_min"], row["denom_max"]) for row in code_100_200) == [
        (100.0, 100.0),
        (200.0, 200.0),
    ]
    assert all(row["frontend_type"] == "code" for row in code_100_200)
    assert all(row["subtype"] == "代码/卡密" for row in code_100_200)
    assert all(row["processing_method"] == "fast_process" for row in code_100_200)
    assert all(row["feedback_note"] == "极速快刷，约1-5分钟" for row in code_100_200)

    card_50 = rows_for("[US横白】卡图50=【5.55】（50倍数）", rows)
    assert len(card_50) == 2
    assert sorted(row["subtype"] for row in card_50) == ["横卡", "白卡"]
    assert all(row["country"] == "US" and row["currency"] == "USD" for row in card_50)
    assert all(row["frontend_type"] == "physical" for row in card_50)
    assert all(row["processing_method"] == "fast_process" for row in card_50)
    assert all(row["subtype"] != "卡图" for row in card_50)

    card_100_150 = rows_for("[US横白】卡图100/150=【5.62】（50倍数）", rows)
    assert len(card_100_150) == 4
    assert sorted((row["subtype"], row["denom_min"], row["denom_max"]) for row in card_100_150) == [
        ("横卡", 100.0, 100.0),
        ("横卡", 150.0, 150.0),
        ("白卡", 100.0, 100.0),
        ("白卡", 150.0, 150.0),
    ]

    card_350_450 = rows_for("[US横白】卡图350/450=【5.72】（50倍数）", rows)
    assert len(card_350_450) == 4

    card_200_500 = rows_for("[US横白】卡图200/300/400/500=【5.72】（50倍数）", rows)
    assert len(card_200_500) == 8
    assert sorted((row["subtype"], row["denom_min"], row["denom_max"]) for row in card_200_500) == [
        ("横卡", 200.0, 200.0),
        ("横卡", 300.0, 300.0),
        ("横卡", 400.0, 400.0),
        ("横卡", 500.0, 500.0),
        ("白卡", 200.0, 200.0),
        ("白卡", 300.0, 300.0),
        ("白卡", 400.0, 400.0),
        ("白卡", 500.0, 500.0),
    ]
    assert all(row["country"] == "US" and row["currency"] == "USD" for row in card_200_500)
    assert all(row["processing_method"] == "fast_process" for row in card_200_500)
    assert not any(row["subtype"] == "卡图" for row in rows if "US横白" in row["source_line"])
    assert all(row["processing_method"] == "fast_process" for row in rows)
    assert all(row["feedback_note"] == "极速快刷，约1-5分钟" for row in rows)


def test_parse_defaults_fill_empty_fields_without_overriding_line_values() -> None:
    rows = parse_quote_text(
        "回归测试群",
        FAST_PROCESS_FIXED_VALUE_SAMPLE,
        default_brand="Apple",
        default_market="UK|GBP",
        default_processing_method="slow_process",
        default_multiplier=100,
    )

    assert len(rows) == 12, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)

    code_50 = rows_for("代码:50=5.25(单张)", rows)
    assert len(code_50) == 1
    assert code_50[0]["brand"] == "Apple"
    assert code_50[0]["country"] == "UK"
    assert code_50[0]["currency"] == "GBP"
    assert code_50[0]["processing_method"] == "fast_process"
    assert code_50[0]["multiplier"] == 50

    card_50 = rows_for("[US横白】卡图50=【5.55】（50倍数）", rows)
    assert card_50
    assert all(row["brand"] == "Apple" for row in card_50)
    assert all(row["country"] == "US" and row["currency"] == "USD" for row in card_50)
    assert all(row["processing_method"] == "fast_process" for row in card_50)
    assert all(row["multiplier"] == 50 for row in card_50)
    assert all(row["raw_card_subtype"] == "横白" for row in card_50)
    assert all(row["normalized_card_subtype"] == "卡图" for row in card_50)


def test_code_fixed_value_separator_variants() -> None:
    cases = [
        ("代码50=5.25(单张)", [(50.0, 50.0)]),
        ("代码:50=5.25(单张)", [(50.0, 50.0)]),
        ("代码：50=5.25(单张)", [(50.0, 50.0)]),
        ("代码 50=5.25(单张)", [(50.0, 50.0)]),
        ("代码100/200=5.42(单张)", [(100.0, 100.0), (200.0, 200.0)]),
        ("代码:100/200=5.42(单张)", [(100.0, 100.0), (200.0, 200.0)]),
        ("代码：100/200=5.42(单张)", [(100.0, 100.0), (200.0, 200.0)]),
    ]
    for source_line, expected_ranges in cases:
        rows = parse_quote_text("回归测试群", f"极速快刷 50倍数 1-5min-\n{source_line}")
        assert len(rows) == len(expected_ranges), source_line
        assert sorted((row["denom_min"], row["denom_max"]) for row in rows) == expected_ranges
        assert all(row["frontend_type"] == "code" for row in rows)
        assert all(row["subtype"] == "代码/卡密" for row in rows)
        assert all(str(row["supplier_rate"]) in {"5.25", "5.42"} for row in rows)
        assert all(row["processing_method"] == "fast_process" for row in rows)
        assert all(row["feedback_note"] == "极速快刷，约1-5分钟" for row in rows)


def test_market_rate_parenthesized_range_sample() -> None:
    rows = parse_quote_text("回归测试群", MARKET_RATE_RANGE_SAMPLE)

    assert len(rows) == 6, len(rows)
    assert not rows_for("苹果卡：卡图", rows)
    assert not rows_for("香港批量卡问~", rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all(row["frontend_type"] == "physical" for row in rows)
    assert all(row["subtype"] == "卡图" for row in rows)
    assert all(row["processing_method"] == "fast_card" for row in rows)
    assert all(row["multiplier"] is None for row in rows)

    expected = [
        ("Hong Kong", "HKD", 500.0, 1500.0, "0.75", "包50H；只要稳卡"),
        ("Hong Kong", "HKD", 1501.0, 3000.0, "0.75", "包50H；只要稳卡"),
        ("Hong Kong", "HKD", 3001.0, 5000.0, "0.75", "包50H；只要稳卡"),
        ("Hong Kong", "HKD", 150.0, 490.0, "0.715", "包6H；只要稳卡"),
        ("US", "USD", 15.0, 100.0, "5.35", ""),
        ("Canada", "CAD", 15.0, 100.0, "3.7", ""),
    ]
    actual = [
        (
            row["country"],
            row["currency"],
            row["denom_min"],
            row["denom_max"],
            str(row["supplier_rate"]),
            row["requirements"],
        )
        for row in rows
    ]
    assert actual == expected

    default_rows = parse_quote_text(
        "回归测试群",
        "美区US 5.35（15-100）",
        default_brand="Apple",
        default_subtype="卡图",
    )
    assert len(default_rows) == 1
    assert default_rows[0]["brand"] == "Apple"
    assert default_rows[0]["subtype"] == "卡图"
    assert default_rows[0]["frontend_type"] == "physical"


def test_two_line_same_rate_sample() -> None:
    rows = parse_quote_text(
        "回归测试群",
        TWO_LINE_SAME_RATE_SAMPLE,
        default_brand="Apple",
    )

    assert len(rows) == 4, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all(row["denom_min"] == 200 for row in rows)
    assert all(row["denom_max"] == 5000 for row in rows)
    assert all(Decimal(str(row["supplier_rate"])) == Decimal("0.475") for row in rows)
    assert all(row["processing_method"] == "fast_card" for row in rows)
    assert all(row["requirements"] == "以上200面值以下不加账；来稳的老客户卡" for row in rows)
    assert not any("单独更新" in row["source_line"] for row in rows)
    assert not any("备注" in row["source_line"] or "要求" in row["source_line"] for row in rows)

    sweden = [row for row in rows if row["country"] == "Sweden" and row["currency"] == "SEK"]
    norway = [row for row in rows if row["country"] == "Norway" and row["currency"] == "NOK"]
    assert len(sweden) == 2
    assert len(norway) == 2
    assert {row["multiplier"] for row in sweden} == {100}
    assert {row["multiplier"] for row in norway} == {50}
    assert {(row["frontend_type"], row["subtype"]) for row in sweden} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }
    assert {(row["frontend_type"], row["subtype"]) for row in norway} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }


def test_razer_steam_unbounded_same_rate() -> None:
    rows = parse_quote_text("回归测试群", RAZER_UNBOUNDED_SAMPLE)
    assert len(rows) == 14, len(rows)
    assert all(row["brand"] == "Razer" for row in rows)
    assert all(row["denom_min"] is None and row["denom_max"] is None for row in rows)
    assert all(row["confidence"] >= 0.8 for row in rows)
    assert not any("【问】" in row["source_line"] for row in rows)

    expected_rates = {
        ("US", "USD"): 5.63,
        ("Singapore", "SGD"): 4.18,
        ("Australia", "AUD"): 3.90,
        ("Canada", "CAD"): 4.00,
        ("Mexico", "MXN"): 0.323,
        ("EU", "EUR"): 5.10,
        ("UK", "GBP"): 5.10,
    }
    for market, expected_rate in expected_rates.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert {(row["frontend_type"], row["subtype"]) for row in market_rows} == {
            ("physical", "卡图"),
            ("code", "代码/卡密"),
        }
        assert all(Decimal(str(row["supplier_rate"])) == Decimal(str(expected_rate)) for row in market_rows)

    for country in ("EU", "UK"):
        assert all("RG10+" in row["requirements"] for row in rows if row["country"] == country)

    steam_rows = parse_quote_text("回归测试群", "==== Steam 蒸汽 ====\n美 USD=5.20")
    assert len(steam_rows) == 2
    assert {(row["frontend_type"], row["subtype"]) for row in steam_rows} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }

    apple_rows = parse_quote_text("回归测试群", "==== Apple 苹果 ====\n美 USD=5.20")
    assert len(apple_rows) == 2
    assert {(row["frontend_type"], row["subtype"]) for row in apple_rows} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }
    assert all(row["denom_min"] is None and row["denom_max"] is None for row in apple_rows)


def test_itunes_electronic_card_aliases_and_context() -> None:
    rows = parse_quote_text("回归测试群", ITUNES_ELECTRONIC_SAMPLE)
    assert len(rows) == 2, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all((row["country"], row["currency"]) == ("US", "USD") for row in rows)
    assert all(row["frontend_type"] == "code" for row in rows)
    assert all(row["subtype"] == "电子卡" for row in rows)
    assert all(row["normalized_card_subtype"] == "电子卡" for row in rows)
    assert all(row["processing_method"] == "fast_process" for row in rows)
    assert all("1-8分钟" in row["feedback_note"] for row in rows)
    assert [
        (row["denom_min"], row["denom_max"], row["multiplier"], str(row["supplier_rate"]))
        for row in rows
    ] == [
        (10.0, 190.0, 5.0, "5.15"),
        (100.0, 500.0, 50.0, "5.50"),
    ]

    for alias in ("电子", "电子卡", "电子图", "e-card", "ecard"):
        alias_rows = parse_quote_text(
            "回归测试群",
            f"【iTune-US 快刷】\nUS-{alias}:10-190=5.15(5倍)",
        )
        assert len(alias_rows) == 1, alias
        assert alias_rows[0]["frontend_type"] == "code", alias
        assert alias_rows[0]["subtype"] == "电子卡", alias

    full_rows = parse_quote_text("回归测试群", ITUNES_FULL_SAMPLE)
    fixed_horizontal = [row for row in full_rows if row["source_line"].startswith("US-横白：100/150")]
    vertical = [row for row in full_rows if row["source_line"].startswith("US-竖卡")]
    assert len(fixed_horizontal) == 2
    assert {(row["subtype"], row["denom_min"], row["denom_max"]) for row in fixed_horizontal} == {
        ("横白", 100.0, 100.0),
        ("横白", 150.0, 150.0),
    }
    assert len(vertical) == 1
    assert vertical[0]["frontend_type"] == "physical"
    assert vertical[0]["subtype"] == "竖卡"
    assert vertical[0]["multiplier"] == 50
    assert vertical[0]["processing_method"] == "fast_process"


def test_card_secret_same_price_context() -> None:
    rows = parse_quote_text(
        "回归测试群",
        CARD_SECRET_SAME_CONTEXT_SAMPLE,
        default_brand="Apple",
    )
    assert len(rows) == 4, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all(row["processing_method"] == "fast_card" for row in rows)
    assert all(row["multiplier"] == 50 for row in rows)
    assert all((row["denom_min"], row["denom_max"]) == (100.0, 4000.0) for row in rows)

    norway = [row for row in rows if (row["country"], row["currency"]) == ("Norway", "NOK")]
    sweden = [row for row in rows if (row["country"], row["currency"]) == ("Sweden", "SEK")]
    assert len(norway) == 2
    assert len(sweden) == 2
    expected_types = {("physical", "卡图"), ("code", "代码/卡密")}
    assert {(row["frontend_type"], row["subtype"]) for row in norway} == expected_types
    assert {(row["frontend_type"], row["subtype"]) for row in sweden} == expected_types
    assert all(Decimal(str(row["supplier_rate"])) == Decimal("0.47") for row in norway)
    assert all(Decimal(str(row["supplier_rate"])) == Decimal("0.46") for row in sweden)

    for keyword in ("密同", "卡密同", "图密同", "图/密同", "图/密同价", "卡图卡密同", "卡图卡密同价"):
        keyword_rows = parse_quote_text(
            "回归测试群",
            f"Apple US {keyword} 100-200=5.20",
        )
        assert len(keyword_rows) == 2, keyword
        assert {(row["frontend_type"], row["subtype"]) for row in keyword_rows} == expected_types


def test_open_ended_denom_range() -> None:
    rows = parse_quote_text("回归测试群", OPEN_ENDED_RANGE_SAMPLE, default_brand="Apple")
    assert len(rows) == 2, len(rows)
    assert all((row["country"], row["currency"]) == ("South Africa", "ZAR") for row in rows)
    assert {(row["frontend_type"], row["subtype"]) for row in rows} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }
    assert all(row["denom_min"] == 200 for row in rows)
    assert all(row["denom_max"] is None for row in rows)
    assert all(Decimal(str(row["supplier_rate"])) == Decimal("0.265") for row in rows)

    cases = [
        ("200以上图/密=0.265", 2),
        ("200以上图=0.265", 1),
        ("200以上密=0.265", 1),
        ("200+图/密=0.265", 2),
        (">=200图/密=0.265", 2),
        ("200以上 图/密 = 0.265", 2),
    ]
    for source_line, expected_count in cases:
        case_rows = parse_quote_text(
            "回归测试群",
            f"====南非====\n{source_line}",
            default_brand="Apple",
        )
        assert len(case_rows) == expected_count, source_line
        assert all(row["denom_min"] == 200 for row in case_rows), source_line
        assert all(row["denom_max"] is None for row in case_rows), source_line
        assert all(Decimal(str(row["supplier_rate"])) == Decimal("0.265") for row in case_rows), source_line


def test_hash_bracket_apple_quotes() -> None:
    rows = parse_quote_text(
        "回归测试群",
        HASH_BRACKET_APPLE_SAMPLE,
        default_brand="Apple",
    )
    assert len(rows) == 21, len(rows)
    assert all(row["source_line"].startswith("#") for row in rows)
    assert all(row["brand"] == "Apple" for row in rows)

    us_image = rows_for("#US      卡图快加【5.21】10-200（5倍数）囤卡，稳发", rows)
    assert len(us_image) == 1
    assert (us_image[0]["country"], us_image[0]["currency"]) == ("US", "USD")
    assert (us_image[0]["frontend_type"], us_image[0]["subtype"]) == ("physical", "卡图")
    assert us_image[0]["processing_method"] == "fast_card"
    assert (us_image[0]["denom_min"], us_image[0]["denom_max"]) == (10.0, 200.0)
    assert us_image[0]["multiplier"] == 5
    assert_money(us_image[0]["supplier_rate"], 5.21)
    assert "囤卡，稳发" in us_image[0]["requirements"]

    us_electronic = rows_for("#US      电子代码快加【5.16】10-200（5倍数）囤卡，稳发", rows)
    assert len(us_electronic) == 1
    assert (us_electronic[0]["frontend_type"], us_electronic[0]["subtype"]) == ("code", "电子卡")
    assert_money(us_electronic[0]["supplier_rate"], 5.16)

    us_secret = rows_for("#US      卡密快加【5.11】面值15-90（5倍数）", rows)
    assert len(us_secret) == 1
    assert (us_secret[0]["frontend_type"], us_secret[0]["subtype"]) == ("code", "代码/卡密")
    assert (us_secret[0]["denom_min"], us_secret[0]["denom_max"]) == (15.0, 90.0)

    cad = [row for row in rows if (row["country"], row["currency"]) == ("Canada", "CAD")]
    assert len(cad) == 2
    assert {(row["frontend_type"], row["subtype"]) for row in cad} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }

    expected_pair_markets = {
        ("UK", "GBP"): 5.8,
        ("Switzerland", "CHF"): 6.0,
        ("Australia", "AUD"): 3.3,
        ("Germany", "EUR"): 4.7,
    }
    for market, expected_rate in expected_pair_markets.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert {(row["frontend_type"], row["subtype"]) for row in market_rows} == {
            ("physical", "卡图"),
            ("code", "代码/卡密"),
        }
        assert all(Decimal(str(row["supplier_rate"])) == Decimal(str(expected_rate)) for row in market_rows)

    japan = [row for row in rows if (row["country"], row["currency"]) == ("Japan", "JPY")]
    assert len(japan) == 2
    assert all((row["denom_min"], row["denom_max"]) == (5000.0, 100000.0) for row in japan)
    assert all(row["multiplier"] == 1000 for row in japan)
    assert all(Decimal(str(row["supplier_rate"])) == Decimal("0.033") for row in japan)

    combined = [row for row in rows if row["country"] in {"Belgium", "Ireland", "Austria"}]
    assert len(combined) == 6
    for country in ("Belgium", "Ireland", "Austria"):
        country_rows = [row for row in combined if row["country"] == country]
        assert len(country_rows) == 2
        assert all(row["currency"] == "EUR" for row in country_rows)
        assert {(row["frontend_type"], row["subtype"]) for row in country_rows} == {
            ("physical", "卡图"),
            ("code", "代码/卡密"),
        }
        assert all((row["denom_min"], row["denom_max"]) == (10.0, 200.0) for row in country_rows)
        assert all(
            row["multiplier"] == 5 and Decimal(str(row["supplier_rate"])) == Decimal("4.7")
            for row in country_rows
        )

    non_quote_lines = {
        "#压90分钟 100us",
        "#卡图电子最多要2连",
        "#ITS不要 #ITS不要 #ITS不要",
        "#包50小时再发",
        "#备注:所有苹果卡任何国家默认多发卡不接受争议哪边加账算哪边",
        "#30分钟内赎回双禁不结账",
    }
    assert not any(row["source_line"] in non_quote_lines for row in rows)
    assert all(row["status"] == "active" for row in rows)


def test_paused_quote_without_rate() -> None:
    rows = parse_quote_text(
        "回归测试群",
        "NZD 10-500 图/密=暂停",
        default_brand="Apple",
    )
    assert len(rows) == 2
    assert {(row["frontend_type"], row["subtype"]) for row in rows} == {
        ("physical", "卡图"),
        ("code", "代码/卡密"),
    }
    assert all((row["country"], row["currency"]) == ("New Zealand", "NZD") for row in rows)
    assert all(row["status"] == "paused" and row["supplier_rate"] is None for row in rows)


def test_razer_multi_market_line_split_and_precision() -> None:
    rows = parse_quote_text("回归测试群", RAZER_MULTI_MARKET_SAMPLE)
    assert len(rows) == 34, len(rows)
    expected_rates = {
        ("EU", "EUR"): "5.3",
        ("UK", "GBP"): "5.3",
        ("Malaysia", "MYR"): "1.44",
        ("Brazil", "BRL"): "1.07",
        ("Mexico", "MXN"): "0.325",
        ("Singapore", "SGD"): "4.26",
        ("Philippines", "PHP"): "0.095",
        ("Canada", "CAD"): "3.98",
        ("Australia", "AUD"): "3.90",
        ("Thailand", "THB"): "0.16",
        ("Colombia", "COP"): "0.001",
        ("Indonesia", "IDR"): "0.00033",
        ("Turkey", "TRY"): "0.12",
        ("India", "INR"): "0.055",
        ("New Zealand", "NZD"): "3.20",
        ("Japan", "JPY"): "0.03",
        ("Chile", "CLP"): "0.001",
    }
    for market, expected_rate in expected_rates.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert {str(row["supplier_rate"]) for row in market_rows} == {expected_rate}
        assert {(row["frontend_type"], row["subtype"]) for row in market_rows} == {
            ("physical", "卡图"),
            ("code", "代码/卡密"),
        }
    assert all(row["status"] == "ask_first" for row in rows if row["country"] in {"EU", "UK", "Japan"})
    assert all(row["status"] == "active" for row in rows if row["country"] in {"Thailand", "Colombia", "Indonesia", "Turkey", "Chile"})

    precision_rows = parse_quote_text("回归测试群", PRECISION_SAMPLE)
    precision_by_source = {
        source: {str(row["supplier_rate"]) for row in precision_rows if row["source_line"] == source}
        for source in ["印尼雷蛇=0.00033", "印度尼西亚-IDR----【0.00018】", "哥伦比亚=0.0011"]
    }
    assert precision_by_source == {
        "印尼雷蛇=0.00033": {"0.00033"},
        "印度尼西亚-IDR----【0.00018】": {"0.00018"},
        "哥伦比亚=0.0011": {"0.0011"},
    }


def test_xbox_multi_market_and_scatter_normalization() -> None:
    rows = parse_quote_text("回归测试群", XBOX_MULTI_MARKET_SAMPLE)
    assert len(rows) == 54, len(rows)
    assert all(row["brand"] == "Xbox" for row in rows)
    assert all(row["multiplier"] == 5 for row in rows)
    assert all("批量问" in row["requirements"] for row in rows)

    us = [row for row in rows if (row["country"], row["currency"]) == ("US", "USD")]
    uk = [row for row in rows if (row["country"], row["currency"]) == ("UK", "GBP")]
    assert len(us) == 2 and len(uk) == 2
    assert all((row["denom_min"], row["denom_max"]) == (10.0, 250.0) for row in us + uk)
    assert {str(row["supplier_rate"]) for row in us} == {"5.26"}
    assert {str(row["supplier_rate"]) for row in uk} == {"5.95"}

    eu = [row for row in rows if (row["country"], row["currency"]) == ("EU", "EUR")]
    assert len(eu) == 2
    assert {(row["frontend_type"], row["subtype"], str(row["supplier_rate"])) for row in eu} == {
        ("physical", "卡图", "5.1"),
        ("code", "代码/卡密", "5.05"),
    }

    expected_unbounded = {
        ("Brazil", "BRL"): "0.82",
        ("Singapore", "SGD"): "3.25",
        ("Canada", "CAD"): "3.3",
        ("New Zealand", "NZD"): "2.75",
        ("Australia", "AUD"): "3.1",
        ("Sweden", "SEK"): "0.44",
        ("Norway", "NOK"): "0.44",
        ("South Korea", "KRW"): "0.0037",
        ("Switzerland", "CHF"): "5.1",
        ("Colombia", "COP"): "0.0011",
        ("Denmark", "DKK"): "0.57",
        ("Mexico", "MXN"): "0.27",
        ("Poland", "PLN"): "1.1",
        ("Czech Republic", "CZK"): "0.15",
        ("Israel", "ILS"): "1.1",
        ("Hong Kong", "HKD"): "0.55",
        ("South Africa", "ZAR"): "0.15",
        ("United Arab Emirates", "AED"): "0.7",
        ("Taiwan", "TWD"): "0.07",
        ("Saudi Arabia", "SAR"): "1.2",
        ("Hungary", "HUF"): "0.009",
        ("Japan", "JPY"): "0.031",
        ("India", "INR"): "0.03",
        ("Chile", "CLP"): "0.002",
    }
    for market, expected_rate in expected_unbounded.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert all(row["denom_min"] is None and row["denom_max"] is None for row in market_rows)
        assert {str(row["supplier_rate"]) for row in market_rows} == {expected_rate}
        assert {(row["frontend_type"], row["subtype"]) for row in market_rows} == {
            ("physical", "卡图"),
            ("code", "代码/卡密"),
        }
    assert all(row["status"] == "ask_first" for row in rows if row["country"] == "Japan")
    assert all(row["status"] == "active" for row in rows if row["country"] == "Hungary")

    scatter = parse_quote_text("回归测试群", "Apple USD散卡 10-190=5.38（5倍数）")
    assert len(scatter) == 1
    assert scatter[0]["frontend_type"] == "physical"
    assert scatter[0]["raw_card_subtype"] == "散卡"
    assert scatter[0]["normalized_card_subtype"] == "卡图"
    assert scatter[0]["multiplier"] == 5

    scatter_override = parse_quote_text("回归测试群", "Apple USD散卡 10-190=5.38（1倍数）")
    assert len(scatter_override) == 1
    assert scatter_override[0]["multiplier"] == 1
    assert "散卡默认5倍" in scatter_override[0]["parse_note"]


def test_xbox_default_same_rate_and_apple_horizontal_white() -> None:
    xbox_rows = parse_quote_text("回归测试群", XBOX_DEFAULT_SAME_RATE_SAMPLE)
    assert len(xbox_rows) == 2
    assert all(row["brand"] == "Xbox" for row in xbox_rows)
    assert all((row["country"], row["currency"]) == ("US", "USD") for row in xbox_rows)
    assert {(row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"]) for row in xbox_rows} == {
        ("physical", "卡图", "卡图"),
        ("code", "代码/卡密", "代码"),
    }
    assert all((row["denom_min"], row["denom_max"]) == (10.0, 250.0) for row in xbox_rows)
    assert all(row["multiplier"] == 5 and str(row["supplier_rate"]) == "5.20" for row in xbox_rows)

    apple_rows = parse_quote_text(
        "回归测试群",
        APPLE_HORIZONTAL_WHITE_SAMPLE,
        default_brand="Apple",
    )
    assert len(apple_rows) == 4, len(apple_rows)
    assert all(row["brand"] == "Apple" for row in apple_rows)
    assert all((row["country"], row["currency"]) == ("US", "USD") for row in apple_rows)
    assert all(row["frontend_type"] == "physical" for row in apple_rows)
    assert {row["raw_card_subtype"] for row in apple_rows} == {"横白"}
    assert all(row["normalized_card_subtype"] == "卡图" for row in apple_rows)
    assert not any(row["subtype"] in {"待确认", "横卡", "白卡"} for row in apple_rows)
    assert all(row["processing_method"] == "fast_process" for row in apple_rows)
    assert all("1-5分钟" in row["feedback_note"] for row in apple_rows)

    fixed_50 = rows_for("US横白:50=5.53 （单张）", apple_rows)
    assert len(fixed_50) == 1
    assert all((row["denom_min"], row["denom_max"]) == (50.0, 50.0) for row in fixed_50)
    assert all("单张固定面值" in row["requirements"] for row in fixed_50)

    fixed_100_150 = rows_for("US横白:100/150=5.68", apple_rows)
    assert len(fixed_100_150) == 2
    assert sorted((row["raw_card_subtype"], row["denom_min"], row["denom_max"]) for row in fixed_100_150) == [
        ("横白", 100.0, 100.0),
        ("横白", 150.0, 150.0),
    ]

    ranged = rows_for("US横白:200-500=5.7 (100倍）", apple_rows)
    assert len(ranged) == 1
    assert all((row["denom_min"], row["denom_max"]) == (200.0, 500.0) for row in ranged)
    assert all(row["multiplier"] == 100 for row in ranged)

    vertical_rows = parse_quote_text("回归测试群", "Xbox\nUS竖卡 10-100=5.0")
    assert len(vertical_rows) == 1
    assert vertical_rows[0]["frontend_type"] == "physical"
    assert vertical_rows[0]["raw_card_subtype"] == "卡图"
    assert vertical_rows[0]["normalized_card_subtype"] == "卡图"
    assert "非 Apple 品牌出现竖卡，已归类为卡图" in vertical_rows[0]["parse_note"]

    electronic_rows = parse_quote_text("回归测试群", "Roblox\nUS电子卡 10-100=3.5")
    assert len(electronic_rows) == 1
    assert (
        electronic_rows[0]["frontend_type"],
        electronic_rows[0]["raw_card_subtype"],
        electronic_rows[0]["normalized_card_subtype"],
    ) == ("code", "电子卡", "电子卡")


def test_roblox_market_rate_matrix() -> None:
    rows = parse_quote_text("回归测试群", ROBLOX_MATRIX_SAMPLE)
    assert len(rows) == 26, len(rows)
    assert all(row["brand"] == "Roblox" for row in rows)
    assert all(row["denom_min"] is None and row["denom_max"] is None for row in rows)
    assert all("RA开头游戏币不要" in row["requirements"] for row in rows)
    assert all("其他国家问" in row["requirements"] for row in rows)

    expected_rates = {
        ("US", "USD"): "3.5",
        ("EU", "EUR"): "3.5",
        ("UK", "GBP"): "3.8",
        ("Canada", "CAD"): "2.2",
        ("Australia", "AUD"): "1.9",
        ("Thailand", "THB"): "0.1",
        ("Mexico", "MXN"): "0.16",
        ("Malaysia", "MYR"): "0.6",
        ("New Zealand", "NZD"): "1.7",
        ("Brazil", "BRL"): "0.5",
        ("Singapore", "SGD"): "2.2",
        ("Sweden", "SEK"): "0.25",
        ("Norway", "NOK"): "0.25",
    }
    for market, expected_rate in expected_rates.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert {str(row["supplier_rate"]) for row in market_rows} == {expected_rate}
        assert {(row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"]) for row in market_rows} == {
            ("physical", "卡图", "卡图"),
            ("code", "代码/卡密", "代码"),
        }
    assert not any(row["source_line"] in {"其他国家问", "（RA开头游戏币不要）"} for row in rows)


def test_psn_market_matrix_and_eur_country_tiers() -> None:
    rows = parse_quote_text("回归测试群", PSN_MATRIX_SAMPLE, default_brand="PSN")
    assert len(rows) == 86, len(rows)
    assert all(row["brand"] == "PSN" for row in rows)
    assert all("批量提前问" in row["requirements"] for row in rows)

    expected_type_pair = {
        ("physical", "卡图", "卡图"),
        ("code", "代码/卡密", "代码"),
    }

    def assert_type_pair(market_rows: list[dict]) -> None:
        assert {
            (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"])
            for row in market_rows
        } == expected_type_pair

    us = [row for row in rows if (row["country"], row["currency"]) == ("US", "USD")]
    assert len(us) == 2
    assert_type_pair(us)
    assert all((row["denom_min"], row["denom_max"]) == (10.0, 200.0) for row in us)
    assert all(str(row["supplier_rate"]) == "3.95" for row in us)
    assert all(row["status"] == "active" for row in us)
    assert all("100以上问" in row["requirements"] for row in us)

    uk = [row for row in rows if (row["country"], row["currency"]) == ("UK", "GBP")]
    assert len(uk) == 2
    assert_type_pair(uk)
    assert all((row["denom_min"], row["denom_max"]) == (5.0, 200.0) for row in uk)
    assert all(str(row["supplier_rate"]) == "4.2" for row in uk)

    eur_markets = {
        "Portugal",
        "Slovakia",
        "Croatia",
        "Ireland",
        "France",
        "Germany",
        "Spain",
        "Netherlands",
        "Austria",
        "Belgium",
        "Italy",
        "Greece",
        "Finland",
        "Slovenia",
    }
    assert not any((row["country"], row["currency"]) == ("EU", "EUR") for row in rows)
    for country in eur_markets:
        market_rows = [row for row in rows if (row["country"], row["currency"]) == (country, "EUR")]
        assert len(market_rows) == 4, country
        tiers = {
            (
                row["frontend_type"],
                row["raw_card_subtype"],
                row["normalized_card_subtype"],
                row["denom_min"],
                row["denom_max"],
                str(row["supplier_rate"]),
            )
            for row in market_rows
        }
        assert tiers == {
            ("physical", "卡图", "卡图", 5.0, 200.0, "3.45"),
            ("code", "代码/卡密", "代码", 5.0, 200.0, "3.45"),
            ("physical", "卡图", "卡图", 200.0, None, "2.8"),
            ("code", "代码/卡密", "代码", 200.0, None, "2.8"),
        }, (country, tiers)

    expected_single_rates = {
        ("Australia", "AUD"): ("1.6", 10.0, 300.0),
        ("New Zealand", "NZD"): ("1.5", None, None),
        ("Denmark", "DKK"): ("0.2", None, None),
        ("Brazil", "BRL"): ("0.6", None, None),
        ("Malaysia", "MYR"): ("0.5", None, None),
        ("Canada", "CAD"): ("1.9", 10.0, 500.0),
        ("Sweden", "SEK"): ("0.23", None, None),
        ("Norway", "NOK"): ("0.23", None, None),
        ("Taiwan", "TWD"): ("0.06", None, None),
        ("Thailand", "THB"): ("0.05", None, None),
        ("Bulgaria", "BGN"): ("1.9", None, None),
        ("Singapore", "SGD"): ("1.7", None, None),
        ("Switzerland", "CHF"): ("3.0", None, None),
    }
    for market, (rate, denom_min, denom_max) in expected_single_rates.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert_type_pair(market_rows)
        assert all(str(row["supplier_rate"]) == rate for row in market_rows)
        assert all((row["denom_min"], row["denom_max"]) == (denom_min, denom_max) for row in market_rows)

    taiwan = [row for row in rows if (row["country"], row["currency"]) == ("Taiwan", "TWD")]
    assert len(taiwan) == 2
    assert all(row["status"] == "ask_first" for row in taiwan)
    assert all(row["denom_min"] is None and row["denom_max"] is None for row in taiwan)

    pure_digital = parse_quote_text("回归测试群", "〖 PSN〗\n纯数字PSN1.5")
    assert len(pure_digital) == 1
    pure_row = pure_digital[0]
    assert pure_row["brand"] == "PSN"
    assert (pure_row["frontend_type"], pure_row["raw_card_subtype"], pure_row["normalized_card_subtype"]) == (
        "code",
        "代码/卡密",
        "代码",
    )
    assert (pure_row["country"], pure_row["currency"]) == ("", "")
    assert str(pure_row["supplier_rate"]) == "1.5"
    assert pure_row["denom_min"] is None and pure_row["denom_max"] is None
    assert "纯数字PSN" in pure_row["requirements"]


def test_amazon_market_aliases_and_distinct_type_rates() -> None:
    rows = parse_quote_text("回归测试群", AMAZON_DUAL_RATE_SAMPLE)
    assert len(rows) == 14, len(rows)
    assert all(row["brand"] == "Amazon" for row in rows)
    assert all("连卡大卡问" in row["requirements"] for row in rows)

    expected = {
        ("US", "USD", 50.0, 200.0): ("5.4", "5.2"),
        ("US", "USD", 201.0, 500.0): ("5.3", "5.1"),
        ("UK", "GBP", 25.0, 200.0): ("5.9", "4.9"),
        ("Germany", "EUR", 25.0, 200.0): ("5.0", "4.0"),
        ("Canada", "CAD", 50.0, 200.0): ("3.3", "2.5"),
        ("Italy", "EUR", 25.0, 200.0): ("4.6", "4.0"),
        ("Australia", "AUD", 25.0, 200.0): ("3.2", "2.6"),
    }
    for key, (physical_rate, code_rate) in expected.items():
        country, currency, denom_min, denom_max = key
        quote_rows = [
            row
            for row in rows
            if (row["country"], row["currency"], row["denom_min"], row["denom_max"]) == key
        ]
        assert len(quote_rows) == 2, key
        actual = {
            (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"]): str(
                row["supplier_rate"]
            )
            for row in quote_rows
        }
        assert actual == {
            ("physical", "卡图", "卡图"): physical_rate,
            ("code", "代码/卡密", "代码"): code_rate,
        }, (key, actual)

    variants = [
        "美亚 50-200=5.4卡图 代码5.2",
        "美亚 50-200=5.4 卡图 代码 5.2",
        "美亚 50-200卡图5.4 代码5.2",
        "美亚 50-200 图5.4 密5.2",
        "美亚 50-200=5.4卡图  代码4.5",
    ]
    for variant in variants:
        variant_rows = parse_quote_text("回归测试群", f"〖Amazon〗\n{variant}")
        assert len(variant_rows) == 2, (variant, variant_rows)
        assert {row["frontend_type"] for row in variant_rows} == {"physical", "code"}
        assert all((row["country"], row["currency"]) == ("US", "USD") for row in variant_rows)
        assert all((row["denom_min"], row["denom_max"]) == (50.0, 200.0) for row in variant_rows)


def test_google_play_dashed_unbounded_physical_quotes() -> None:
    rows = parse_quote_text("回归测试群", GOOGLE_PLAY_DASHED_SAMPLE)
    assert len(rows) == 18, len(rows)
    assert all(row["brand"] == "Google Play" for row in rows)
    assert all(row["frontend_type"] == "physical" for row in rows)
    assert all(row["raw_card_subtype"] == "卡图" for row in rows)
    assert all(row["normalized_card_subtype"] == "卡图" for row in rows)
    assert all(row["denom_min"] is None and row["denom_max"] is None for row in rows)
    assert not any(row["frontend_type"] == "code" for row in rows)
    assert all("连卡代码提前问.不要直接发" in row["requirements"] for row in rows)

    expected_rates = {
        ("US", "USD"): "4.4",
        ("Germany", "EUR"): "3.8",
        ("UK", "GBP"): "3.7",
        ("Switzerland", "CHF"): "3.7",
        ("Canada", "CAD"): "2.5",
        ("Australia", "AUD"): "2.0",
        ("New Zealand", "NZD"): "1.8",
        ("Poland", "PLN"): "0.2",
        ("Japan", "JPY"): "275",
        ("Saudi Arabia", "SAR"): "0.5",
        ("United Arab Emirates", "AED"): "0.6",
        ("Mexico", "MXN"): "0.11",
        ("South Africa", "ZAR"): "0.11",
        ("India", "INR"): "0.032",
        ("Indonesia", "IDR"): "0.00018",
        ("Turkey", "TRY"): "0.05",
        ("Hong Kong", "HKD"): "0.32",
        ("South Korea", "KRW"): "26",
    }
    for market, expected_rate in expected_rates.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 1, market
        assert str(market_rows[0]["supplier_rate"]) == expected_rate

    japan = next(row for row in rows if row["country"] == "Japan")
    korea = next(row for row in rows if row["country"] == "South Korea")
    indonesia = next(row for row in rows if row["country"] == "Indonesia")
    assert "1W等于1*275" in japan["requirements"]
    assert "1W等于1*26" in korea["requirements"]
    assert str(indonesia["supplier_rate"]) == "0.00018"
    assert not any("连卡代码提前问" in row["source_line"] for row in rows)


def test_paysafecard_and_global_default_same_rate() -> None:
    rows = parse_quote_text("回归测试群", PAYSAFECARD_DEFAULT_SAME_RATE_SAMPLE)
    assert len(rows) == 28, len(rows)
    assert all(row["brand"] == "Paysafecard" for row in rows)
    assert all("其他国家问" in row["requirements"] for row in rows)
    assert all("发前问" in row["requirements"] for row in rows)
    assert not any(row["raw_card_subtype"] == "电子卡" for row in rows)
    assert not any(row["normalized_card_subtype"] == "电子卡" for row in rows)

    expected = {
        ("EU", "EUR"): ("6.43", 50.0, 500.0),
        ("Switzerland", "CHF"): ("6.8", 50.0, 500.0),
        ("UK", "GBP"): ("7.15", 50.0, 500.0),
        ("Greece", "EUR"): ("5.7", 50.0, 500.0),
        ("Portugal", "EUR"): ("5.7", 50.0, 500.0),
        ("Norway", "NOK"): ("0.55", 150.0, 5000.0),
        ("Sweden", "SEK"): ("0.56", 150.0, 5000.0),
        ("Romania", "RON"): ("1.1", 100.0, 1000.0),
        ("Poland", "PLN"): ("1.35", 50.0, 500.0),
        ("Denmark", "DKK"): ("0.7", 100.0, 5000.0),
        ("Hungary", "HUF"): ("0.015", 5000.0, 50000.0),
        ("Czech Republic", "CZK"): ("0.24", 300.0, 3000.0),
        ("Australia", "AUD"): ("3.2", 25.0, 500.0),
        ("Canada", "CAD"): ("3.6", 25.0, 500.0),
    }
    expected_pair = {
        ("physical", "卡图", "卡图"),
        ("code", "代码/卡密", "代码"),
    }
    for market, (rate, denom_min, denom_max) in expected.items():
        market_rows = [row for row in rows if (row["country"], row["currency"]) == market]
        assert len(market_rows) == 2, market
        assert {
            (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"])
            for row in market_rows
        } == expected_pair
        assert all(str(row["supplier_rate"]) == rate for row in market_rows)
        assert all((row["denom_min"], row["denom_max"]) == (denom_min, denom_max) for row in market_rows)

    hungary = [row for row in rows if (row["country"], row["currency"]) == ("Hungary", "HUF")]
    assert len(hungary) == 2
    assert all(row["status"] == "ask_first" for row in hungary)
    assert all(str(row["supplier_rate"]) == "0.015" for row in hungary)
    assert all(row["status"] == "active" for row in rows if row["country"] != "Hungary")

    generic_rows = parse_quote_text(
        "回归测试群",
        "US 10-100=5.0",
        default_brand="TestBrand",
    )
    assert len(generic_rows) == 2
    assert all(row["brand"] == "TestBrand" for row in generic_rows)
    assert {
        (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"])
        for row in generic_rows
    } == expected_pair


def test_long_tail_default_us_and_multiple_range_rates() -> None:
    rows = parse_quote_text("回归测试群", LONG_TAIL_MULTI_RANGE_SAMPLE)
    assert len(rows) == 8, len(rows)
    assert all((row["country"], row["currency"]) == ("US", "USD") for row in rows)
    assert all("默认美国 / US / USD" in row["parse_note"] for row in rows)

    expected = {
        ("Sephora", 50.0, 99.0): "4.3",
        ("Sephora", 100.0, 500.0): "4.8",
        ("Footlocker", 50.0, 99.0): "4.4",
        ("Footlocker", 100.0, 500.0): "5.3",
    }
    expected_pair = {
        ("physical", "卡图", "卡图"),
        ("code", "代码/卡密", "代码"),
    }
    for key, rate in expected.items():
        brand, denom_min, denom_max = key
        quote_rows = [
            row
            for row in rows
            if (row["brand"], row["denom_min"], row["denom_max"]) == key
        ]
        assert len(quote_rows) == 2, key
        assert {str(row["supplier_rate"]) for row in quote_rows} == {rate}
        assert {
            (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"])
            for row in quote_rows
        } == expected_pair

    default_market_rows = parse_quote_text(
        "回归测试群",
        "Sephora 50-99=4.3 100-500=4.8",
        default_market="UK|GBP",
    )
    assert all((row["country"], row["currency"]) == ("UK", "GBP") for row in default_market_rows)

    visa_rows = parse_quote_text(
        "回归测试群",
        "Visa 50-99=4.3 100-150=4.6 300-400=4.4 151-299=4.2 500=4.5",
    )
    assert len(visa_rows) == 10
    fixed_500 = [row for row in visa_rows if (row["denom_min"], row["denom_max"]) == (500.0, 500.0)]
    assert len(fixed_500) == 2
    assert all("单张固定面值" in row["requirements"] for row in fixed_500)

    macy_rows = parse_quote_text("回归测试群", "Macy/9 50-99=4.6 100-300=5.1")
    assert len(macy_rows) == 4
    assert all(row["brand"] == "Macy" for row in macy_rows)
    assert all("品牌变体：Macy/9" in row["requirements"] for row in macy_rows)

    ignored_items: list[str] = []
    ask_rows = parse_quote_text(
        "回归测试群",
        "Nike 150-500=ask",
        ignored_items=ignored_items,
    )
    assert ask_rows == []
    assert ignored_items == ["Nike 150-500=ask：无明确价格，已忽略。"]


def test_apple_loose_ranges_multiplier_context_and_europe_groups() -> None:
    for range_text in ["50-200", "50~200", "50～200", "50—200", "50 至 200"]:
        rows = parse_quote_text(
            "回归测试群",
            f"瑞士：整卡卡图：{range_text} 6.35",
            default_brand="Apple",
        )
        assert len(rows) == 1, (range_text, rows)
        row = rows[0]
        assert (row["country"], row["currency"]) == ("Switzerland", "CHF")
        assert (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"]) == (
            "physical",
            "整卡",
            "卡图",
        )
        assert (row["denom_min"], row["denom_max"]) == (50.0, 200.0)
        assert str(row["supplier_rate"]) == "6.35"

    europe_rows = parse_quote_text(
        "回归测试群",
        APPLE_LOOSE_EUROPE_SAMPLE,
        default_brand="Apple",
    )
    assert len(europe_rows) == 8, len(europe_rows)
    assert {row["country"] for row in europe_rows} == {"Belgium", "Italy", "Austria", "Finland"}
    assert not any(row["country"] == "EU" for row in europe_rows)
    assert all(row["currency"] == "EUR" for row in europe_rows)
    assert all((row["denom_min"], row["denom_max"]) == (100.0, None) for row in europe_rows)
    assert all(row["multiplier"] == 10 for row in europe_rows)
    assert all(str(row["supplier_rate"]) == "5.13" for row in europe_rows)
    assert not any(str(row["supplier_rate"]) == "10" for row in europe_rows)
    for country in {"Belgium", "Italy", "Austria", "Finland"}:
        country_rows = [row for row in europe_rows if row["country"] == country]
        assert {
            (row["frontend_type"], row["raw_card_subtype"], row["normalized_card_subtype"])
            for row in country_rows
        } == {
            ("physical", "卡图", "卡图"),
            ("code", "代码/卡密", "代码"),
        }

    multiplier_only = parse_quote_text(
        "回归测试群",
        "面值：100倍数\n整卡卡图：50倍数",
        default_brand="Apple",
    )
    assert multiplier_only == []

    fixed_rows = parse_quote_text(
        "回归测试群",
        "瑞士：\n面值：250 6.32",
        default_brand="Apple",
    )
    assert len(fixed_rows) == 2
    assert all((row["denom_min"], row["denom_max"]) == (250.0, 250.0) for row in fixed_rows)
    assert all(str(row["supplier_rate"]) == "6.32" for row in fixed_rows)

    swiss_block = parse_quote_text(
        "回归测试群",
        "瑞士：\n整卡卡图：50~200 6.35\n面值：250 6.32\n来稳的老客户卡，不稳不要发",
        default_brand="Apple",
    )
    assert len(swiss_block) == 2
    assert all(row["raw_card_subtype"] == "整卡" for row in swiss_block)
    assert all(row["normalized_card_subtype"] == "卡图" for row in swiss_block)
    assert all("来稳的老客户卡，不稳不要发" in row["requirements"] for row in swiss_block)

    combined_only = parse_quote_text(
        "回归测试群",
        "比/意/奥/ 5.13",
        default_brand="Apple",
    )
    assert len(combined_only) == 6
    assert {row["country"] for row in combined_only} == {"Belgium", "Italy", "Austria"}
    assert all(str(row["supplier_rate"]) == "5.13" for row in combined_only)


def test_numeric_role_priority_blocks_multiplier_prices_with_market_context() -> None:
    context_cases = [
        ("倍数：10倍数 100+", 10.0, 100.0),
        ("整卡卡图：50倍数", 50.0, None),
        ("面值：1000倍数", 1000.0, None),
    ]
    for line, multiplier, open_minimum in context_cases:
        roles = classify_numbers_in_line(line)
        assert roles["multiplier"] == multiplier
        assert roles["open_range_min"] == open_minimum
        assert roles["supplier_rate_candidates"] == []
        assert parse_quote_text(
            "回归测试群",
            f"Apple 瑞士\n{line}",
            default_brand="Apple",
        ) == []

    for range_text in ["50-200", "50~200", "50～200", "50—200", "50 至 200"]:
        roles = classify_numbers_in_line(f"瑞士：整卡卡图：{range_text} 6.35")
        assert (roles["range_min"], roles["range_max"]) == (50.0, 200.0)
        assert [item["value"] for item in roles["supplier_rate_candidates"]] == [Decimal("6.35")]

    inherited_rows = parse_quote_text(
        "回归测试群",
        "倍数：10倍数 100+\n芬兰 5.13",
        default_brand="Apple",
    )
    assert len(inherited_rows) == 2
    assert all((row["country"], row["currency"]) == ("Finland", "EUR") for row in inherited_rows)
    assert all((row["denom_min"], row["denom_max"]) == (100.0, None) for row in inherited_rows)
    assert all(row["multiplier"] == 10 for row in inherited_rows)
    assert all(row["supplier_rate"] == Decimal("5.13") for row in inherited_rows)

    combined_rows = parse_quote_text(
        "回归测试群",
        "倍数：10倍数 100+\n比/意/奥/ 5.13",
        default_brand="Apple",
    )
    assert len(combined_rows) == 6
    assert {row["country"] for row in combined_rows} == {"Belgium", "Italy", "Austria"}
    assert all((row["denom_min"], row["denom_max"]) == (100.0, None) for row in combined_rows)
    assert all(row["multiplier"] == 10 for row in combined_rows)
    assert all(row["supplier_rate"] == Decimal("5.13") for row in combined_rows)


def test_parse_apple_itunes_complex_block() -> None:
    rows = parse_quote_text("回归测试群", APPLE_COMPLEX_BLOCK_SAMPLE)
    assert len(rows) == 21, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert not any(row["supplier_rate"] in {Decimal("10"), Decimal("50"), Decimal("1000")} for row in rows)

    germany = [row for row in rows if row["country"] == "Germany"]
    assert len(germany) == 1
    assert (germany[0]["denom_min"], germany[0]["denom_max"], germany[0]["multiplier"]) == (50.0, 250.0, 50.0)
    assert (germany[0]["frontend_type"], germany[0]["raw_card_subtype"], germany[0]["normalized_card_subtype"]) == ("physical", "整卡", "卡图")
    assert germany[0]["supplier_rate"] == Decimal("5.13")
    assert "来稳的老客户卡，不稳不要发" in germany[0]["requirements"]

    poland = [row for row in rows if row["country"] == "Poland"]
    assert len(poland) == 2
    assert {(row["frontend_type"], row["normalized_card_subtype"]) for row in poland} == {("physical", "卡图"), ("code", "代码")}
    assert all((row["denom_min"], row["denom_max"], row["multiplier"]) == (100.0, None, 10.0) for row in poland)
    assert all(row["supplier_rate"] == Decimal("1.3") for row in poland)
    assert all("50以下面值不加账" in row["requirements"] for row in poland)
    assert all("连卡多发提醒一下，否则赎回减账" in row["requirements"] for row in poland)

    uk = [row for row in rows if row["country"] == "UK"]
    assert len(uk) == 1
    assert (uk[0]["frontend_type"], uk[0]["raw_card_subtype"], uk[0]["normalized_card_subtype"]) == ("physical", "整卡/散卡", "卡图")
    assert (uk[0]["denom_min"], uk[0]["denom_max"], uk[0]["multiplier"]) == (15.0, 200.0, 5.0)
    assert uk[0]["supplier_rate"] == Decimal("5.88")

    eu_countries = {"Netherlands", "France", "Spain", "Belgium", "Italy", "Austria", "Finland"}
    eu_rows = [row for row in rows if row["country"] in eu_countries]
    assert len(eu_rows) == 7
    assert {row["country"] for row in eu_rows} == eu_countries
    assert all(row["frontend_type"] == "physical" for row in eu_rows)
    assert all((row["raw_card_subtype"], row["normalized_card_subtype"]) == ("整卡", "卡图") for row in eu_rows)
    assert all(row["multiplier"] == 50 for row in eu_rows)
    assert all(row["denom_min"] is None and row["denom_max"] is None for row in eu_rows)
    assert not any(row["country"] == "EU" for row in rows)

    switzerland = [row for row in rows if row["country"] == "Switzerland"]
    assert len(switzerland) == 2
    assert all(row["frontend_type"] == "physical" for row in switzerland)
    assert all(row["raw_card_subtype"] == "整卡" for row in switzerland)
    assert all(row["multiplier"] is None for row in switzerland)
    assert {(row["denom_min"], row["denom_max"], row["supplier_rate"]) for row in switzerland} == {
        (50.0, 200.0, Decimal("6.35")),
        (250.0, 250.0, Decimal("6.32")),
    }

    for country, denom, multiplier, rate in [
        ("New Zealand", (50.0, 500.0), 50.0, Decimal("3.1")),
        ("Australia", (50.0, 300.0), 50.0, Decimal("3.45")),
    ]:
        country_rows = [row for row in rows if row["country"] == country]
        assert len(country_rows) == 1
        assert (country_rows[0]["denom_min"], country_rows[0]["denom_max"]) == denom
        assert country_rows[0]["multiplier"] == multiplier
        assert country_rows[0]["supplier_rate"] == rate

    japan = [row for row in rows if row["country"] == "Japan"]
    assert len(japan) == 2
    assert all(row["frontend_type"] == "physical" for row in japan)
    assert all(row["multiplier"] == 1000 for row in japan)
    assert {(row["denom_min"], row["denom_max"], row["supplier_rate"]) for row in japan} == {
        (10000.0, 50000.0, Decimal("0.0355")),
        (60000.0, 100000.0, Decimal("0.034")),
    }

    for country, multiplier, rate in [
        ("Sweden", 100.0, Decimal("0.47")),
        ("Norway", 50.0, Decimal("0.475")),
    ]:
        country_rows = [row for row in rows if row["country"] == country]
        assert len(country_rows) == 2
        assert {(row["frontend_type"], row["normalized_card_subtype"]) for row in country_rows} == {("physical", "卡图"), ("code", "代码")}
        assert all((row["denom_min"], row["denom_max"], row["multiplier"]) == (200.0, 5000.0, multiplier) for row in country_rows)
        assert all(row["supplier_rate"] == rate for row in country_rows)
        assert all("以上200面值以下不加账" in row["requirements"] for row in country_rows)
        assert all("来稳的老客户卡" in row["requirements"] for row in country_rows)


def test_parse_apple_bracketed_country_blocks() -> None:
    rows = parse_quote_text(
        "回归测试群",
        APPLE_BRACKETED_COUNTRY_BLOCK_SAMPLE,
        default_brand="Apple",
    )
    assert len(rows) == 33, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all(row["frontend_type"] == "physical" for row in rows)
    assert all(row["raw_card_subtype"] == "卡图" for row in rows)
    assert all(row["normalized_card_subtype"] == "卡图" for row in rows)
    assert not any(row["frontend_type"] == "code" for row in rows)
    assert not any(not row["country"] or not row["currency"] for row in rows)
    assert not any(row["country"] == "EU" for row in rows)

    us = [row for row in rows if row["country"] == "US"]
    assert len(us) == 1
    assert (us[0]["currency"], us[0]["denom_min"], us[0]["denom_max"], us[0]["multiplier"], us[0]["supplier_rate"]) == (
        "USD", 10.0, 195.0, 5.0, Decimal("5.4")
    )
    assert "US代码不收" in us[0]["requirements"]
    assert "50/100/150面值不要" in us[0]["requirements"]
    assert "Redeem Now不要" in us[0]["requirements"]
    assert "纸质发票不要" in us[0]["requirements"]
    assert "电子图不要" in us[0]["requirements"]

    canada = [row for row in rows if row["country"] == "Canada"]
    assert len(canada) == 1
    assert (canada[0]["currency"], canada[0]["denom_min"], canada[0]["denom_max"], canada[0]["multiplier"], canada[0]["supplier_rate"]) == (
        "CAD", 10.0, 190.0, 5.0, Decimal("3.7")
    )

    germany = [row for row in rows if row["country"] == "Germany"]
    assert len(germany) == 3
    assert {(row["denom_min"], row["denom_max"], row["multiplier"], row["supplier_rate"]) for row in germany} == {
        (5.0, 195.0, 5.0, Decimal("5.1")),
        (50.0, 150.0, 50.0, Decimal("5.15")),
        (200.0, 200.0, 50.0, Decimal("5.15")),
    }

    six_country_group = {"Belgium", "Ireland", "Austria", "Italy", "Netherlands", "Finland"}
    for country in six_country_group:
        country_rows = [row for row in rows if row["country"] == country]
        assert len(country_rows) == 3, country
        assert {(row["denom_min"], row["denom_max"], row["supplier_rate"]) for row in country_rows} == {
            (50.0, 200.0, Decimal("5.15")),
            (200.0, 200.0, Decimal("5.15")),
            (250.0, 250.0, Decimal("5.1")),
        }
        assert all(row["multiplier"] == 50 for row in country_rows)

    for country in {"France", "Spain"}:
        country_rows = [row for row in rows if row["country"] == country]
        assert len(country_rows) == 3, country
        assert {(row["denom_min"], row["denom_max"], row["supplier_rate"]) for row in country_rows} == {
            (50.0, 200.0, Decimal("5.18")),
            (200.0, 200.0, Decimal("5.18")),
            (250.0, 250.0, Decimal("5.13")),
        }

    australia = [row for row in rows if row["country"] == "Australia"]
    assert len(australia) == 4
    assert {(row["denom_min"], row["denom_max"], row["supplier_rate"]) for row in australia} == {
        (50.0, 150.0, Decimal("3.4")),
        (10.0, 10.0, Decimal("3.4")),
        (20.0, 20.0, Decimal("3.4")),
        (30.0, 30.0, Decimal("3.4")),
    }
    assert [row for row in australia if row["denom_min"] == 50][0]["multiplier"] == 50
    assert all(row["multiplier"] is None for row in australia if row["denom_min"] in {10.0, 20.0, 30.0})
    assert all("法国" not in row["requirements"] and "西班牙" not in row["requirements"] for row in australia)


def test_parse_apple_itunes_bracket_market_subtype_format() -> None:
    rows = parse_quote_text(
        "回归测试群",
        APPLE_BRACKET_MARKET_SUBTYPE_SAMPLE,
        default_brand="Apple",
    )
    assert len(rows) == 7, len(rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all(row["frontend_type"] == "physical" for row in rows)
    assert all(row["normalized_card_subtype"] == "卡图" for row in rows)
    assert not any(row["frontend_type"] == "code" for row in rows)
    assert not any(not row["country"] or not row["currency"] for row in rows)

    us = [row for row in rows if row["country"] == "US"]
    assert len(us) == 1
    assert (us[0]["currency"], us[0]["raw_card_subtype"]) == ("USD", "散卡")
    assert (us[0]["denom_min"], us[0]["denom_max"], us[0]["supplier_rate"], us[0]["multiplier"]) == (
        10.0, 190.0, Decimal("5.4"), 5.0
    )
    for requirement in [
        "审图",
        "屏幕/模糊/局部电子一律不拿",
        "沃尔玛电子图一律不要",
        "电子图请发带时间/网址的完整截图",
    ]:
        assert requirement in us[0]["requirements"]

    canada = [row for row in rows if row["country"] == "Canada"]
    assert len(canada) == 2
    cad_scattered = [row for row in canada if row["raw_card_subtype"] == "散卡"]
    cad_whole = [row for row in canada if row["raw_card_subtype"] == "整卡"]
    assert len(cad_scattered) == len(cad_whole) == 1
    assert (cad_scattered[0]["denom_min"], cad_scattered[0]["denom_max"], cad_scattered[0]["supplier_rate"], cad_scattered[0]["multiplier"]) == (
        10.0, 500.0, Decimal("3.73"), 5.0
    )
    assert (cad_whole[0]["denom_min"], cad_whole[0]["denom_max"], cad_whole[0]["supplier_rate"], cad_whole[0]["multiplier"]) == (
        100.0, 500.0, Decimal("3.73"), 50.0
    )
    assert cad_whole[0]["processing_method"] == "fast_card"

    australia = [row for row in rows if row["country"] == "Australia"]
    assert len(australia) == 2
    aud_scattered = [row for row in australia if row["raw_card_subtype"] == "散卡"]
    aud_whole = [row for row in australia if row["raw_card_subtype"] == "整卡"]
    assert len(aud_scattered) == len(aud_whole) == 1
    assert (aud_scattered[0]["denom_min"], aud_scattered[0]["denom_max"], aud_scattered[0]["supplier_rate"], aud_scattered[0]["multiplier"]) == (
        20.0, 500.0, Decimal("3.35"), 10.0
    )
    assert (aud_whole[0]["denom_min"], aud_whole[0]["denom_max"], aud_whole[0]["supplier_rate"], aud_whole[0]["multiplier"]) == (
        100.0, 300.0, Decimal("3.4"), 50.0
    )
    assert aud_whole[0]["processing_method"] == "fast_card"
    assert all("囤卡/不熟悉/不稳/别发" in row["requirements"] for row in canada + australia)
    assert all("电子图请发" not in row["requirements"] for row in canada + australia)

    germany = [row for row in rows if row["country"] == "Germany"]
    assert len(germany) == 2
    german_scattered = [row for row in germany if row["raw_card_subtype"] == "散卡"]
    german_horizontal = [row for row in germany if row["raw_card_subtype"] == "横白"]
    assert len(german_scattered) == len(german_horizontal) == 1
    assert (german_scattered[0]["denom_min"], german_scattered[0]["denom_max"], german_scattered[0]["supplier_rate"], german_scattered[0]["multiplier"]) == (
        10.0, 200.0, Decimal("5.1"), 5.0
    )
    assert "连卡问" in german_scattered[0]["requirements"]
    assert (german_horizontal[0]["denom_min"], german_horizontal[0]["denom_max"], german_horizontal[0]["supplier_rate"]) == (
        100.0, 250.0, Decimal("5.1")
    )
    assert german_horizontal[0]["processing_method"] == "fast_card"
    assert all("囤卡/不熟悉" not in row["requirements"] for row in germany)


def main() -> None:
    test_fast_process_fixed_value_sample()
    test_parse_defaults_fill_empty_fields_without_overriding_line_values()
    test_code_fixed_value_separator_variants()
    test_market_rate_parenthesized_range_sample()
    test_two_line_same_rate_sample()
    test_razer_steam_unbounded_same_rate()
    test_itunes_electronic_card_aliases_and_context()
    test_card_secret_same_price_context()
    test_open_ended_denom_range()
    test_hash_bracket_apple_quotes()
    test_paused_quote_without_rate()
    test_razer_multi_market_line_split_and_precision()
    test_xbox_multi_market_and_scatter_normalization()
    test_xbox_default_same_rate_and_apple_horizontal_white()
    test_roblox_market_rate_matrix()
    test_psn_market_matrix_and_eur_country_tiers()
    test_amazon_market_aliases_and_distinct_type_rates()
    test_google_play_dashed_unbounded_physical_quotes()
    test_paysafecard_and_global_default_same_rate()
    test_long_tail_default_us_and_multiple_range_rates()
    test_apple_loose_ranges_multiplier_context_and_europe_groups()
    test_numeric_role_priority_blocks_multiplier_prices_with_market_context()
    test_parse_apple_itunes_complex_block()
    test_parse_apple_bracketed_country_blocks()
    test_parse_apple_itunes_bracket_market_subtype_format()
    fast_rows = parse_quote_text("回归测试群", FAST_PROCESS_FIXED_VALUE_SAMPLE)
    market_rows = parse_quote_text("回归测试群", MARKET_RATE_RANGE_SAMPLE)
    paired_rows = parse_quote_text("回归测试群", TWO_LINE_SAME_RATE_SAMPLE, default_brand="Apple")
    razer_rows = parse_quote_text("回归测试群", RAZER_UNBOUNDED_SAMPLE)
    electronic_rows = parse_quote_text("回归测试群", ITUNES_ELECTRONIC_SAMPLE)
    same_price_rows = parse_quote_text(
        "回归测试群", CARD_SECRET_SAME_CONTEXT_SAMPLE, default_brand="Apple"
    )
    open_ended_rows = parse_quote_text("回归测试群", OPEN_ENDED_RANGE_SAMPLE, default_brand="Apple")
    hash_bracket_rows = parse_quote_text("回归测试群", HASH_BRACKET_APPLE_SAMPLE, default_brand="Apple")
    multi_market_rows = parse_quote_text("回归测试群", RAZER_MULTI_MARKET_SAMPLE)
    xbox_rows = parse_quote_text("回归测试群", XBOX_MULTI_MARKET_SAMPLE)
    apple_horizontal_rows = parse_quote_text(
        "回归测试群", APPLE_HORIZONTAL_WHITE_SAMPLE, default_brand="Apple"
    )
    roblox_rows = parse_quote_text("回归测试群", ROBLOX_MATRIX_SAMPLE)
    psn_rows = parse_quote_text("回归测试群", PSN_MATRIX_SAMPLE, default_brand="PSN")
    amazon_rows = parse_quote_text("回归测试群", AMAZON_DUAL_RATE_SAMPLE)
    google_play_rows = parse_quote_text("回归测试群", GOOGLE_PLAY_DASHED_SAMPLE)
    paysafecard_rows = parse_quote_text("回归测试群", PAYSAFECARD_DEFAULT_SAME_RATE_SAMPLE)
    long_tail_rows = parse_quote_text("回归测试群", LONG_TAIL_MULTI_RANGE_SAMPLE)
    apple_loose_rows = parse_quote_text(
        "回归测试群", APPLE_LOOSE_EUROPE_SAMPLE, default_brand="Apple"
    )
    print(
        f"parser regression passed: fast={len(fast_rows)} rows, "
        f"market={len(market_rows)} rows, paired={len(paired_rows)} rows, "
        f"razer={len(razer_rows)} rows, electronic={len(electronic_rows)} rows, "
        f"same_price={len(same_price_rows)} rows, open_ended={len(open_ended_rows)} rows, "
        f"hash_bracket={len(hash_bracket_rows)} rows, multi_market={len(multi_market_rows)} rows, "
        f"xbox={len(xbox_rows)} rows, apple_horizontal={len(apple_horizontal_rows)} rows, "
        f"roblox={len(roblox_rows)} rows, psn={len(psn_rows)} rows, "
        f"amazon={len(amazon_rows)} rows, google_play={len(google_play_rows)} rows"
        f", paysafecard={len(paysafecard_rows)} rows, long_tail={len(long_tail_rows)} rows"
        f", apple_loose={len(apple_loose_rows)} rows"
    )


if __name__ == "__main__":
    main()
