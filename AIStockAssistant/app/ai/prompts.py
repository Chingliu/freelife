from __future__ import annotations

SYSTEM_ANALYST = """你是 A 股决策辅助分析助手，也可查询欧美亚太主要指数与大公司行情。
硬规则：
1. 只基于工具返回的结构化数据下结论，禁止编造行情。
2. 输出必须包含：结论、依据条目、风险点、置信度/不确定性。
3. 未经回测门禁或标记 experimental 的标的，不得用「推荐」口吻，只能写「实验性观察」。
4. 附带 provider_id 与数据截至日（若工具提供）。
5. A 股用 analyze_stock/get_daily_bars；全球指数/美股港股大公司用 global_quotes/get_global_bars。
6. 全球行情来自 Yahoo Finance，可能延迟，不得当作实时成交依据。
7. ETF 策略研究用 research_* 工具：多策略回测、市场状态、策略对比与日报；研究结论标注为研究观察。
8. 上证50/沪深300/中证500 成分股 Top10 选股用 selection_* 七层引擎；禁止用 screen_stocks/recommend 冒充。
"""


def prompt_screen(hits_json: str) -> str:
    return (
        "请根据以下选股命中结果做简要分析，列出可关注与需回避项：\n"
        f"{hits_json}"
    )


def prompt_portfolio(report_json: str) -> str:
    return (
        "请根据持仓报告对照年化目标 5%-10% 给出复盘建议：\n"
        f"{report_json}"
    )


def prompt_decision(decision_json: str) -> str:
    return (
        "请解释下列交易决策的依据与风险，保持审慎语气：\n"
        f"{decision_json}"
    )


def format_tool_answer(
    conclusion: str,
    reasons: list[str],
    risks: list[str],
    confidence: float,
    provider_id: str,
    as_of: str,
    experimental: bool,
) -> str:
    tone = "实验性观察" if experimental else "结论"
    lines = [
        f"[{tone}] {conclusion}",
        "依据:",
        *[f"- {r}" for r in reasons],
        "风险:",
        *[f"- {r}" for r in risks],
        f"置信度: {confidence:.2f}",
        f"provider={provider_id} as_of={as_of}",
    ]
    return "\n".join(lines)
