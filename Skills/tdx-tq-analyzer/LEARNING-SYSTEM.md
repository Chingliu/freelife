# A股技术分析学习系统（tdx-tq-analyzer）

本目录在原有通达信 TQ 采集、量价分析和研究观察报告基础上，增量提供系统课程、每日学习、练习记录和复习调度。改造范围仅限本 Skill。

## 当前实现

- 六章课程目录：K线基础、成交量、趋势分析、多周期分析、技术指标、量价综合。
- 首期 MVP：前两章 20 个知识点；其余四章建立课程目标和知识点目录。
- 标准库学习调度器：掌握度、到期复习、确定性每日计划。
- 独立单 HTML 学习报告：课程浏览、自测、学习记录、浏览器本地保存、JSON 导入/导出。
- 可选加载原分析流程生成的 `chart_*.json`；没有真实行情数据时明确提示，不伪造K线。

## 运行

在本目录运行：

```bash
python scripts/learning_engine.py --print-plan
python scripts/learning_report.py --out learning_report.html
python scripts/learning_report.py --chart C:/reports/chart_510330_SH.json --out learning_report.html
```

HTML 可离线打开，不依赖 CDN、Web 服务、Node、外部字体或外部 JS/CSS。进度可在浏览器内导出 JSON 备份；如需由 Python 保存统一状态，可用：

```bash
python scripts/learning_engine.py --record K001 3 3 --quality 4
```

## 数据边界

原有 TQ 采集目前约覆盖 105 个交易日日线，不能据此承诺六章所有知识点均有足够案例。每日一图只有在提供真实 `chart_*.json` 时才显示行情K线；未提供时显示数据缺失提示。课程示意和自测不冒充真实行情案例。

## 现阶段限制

- 练习首期为知识理解自测，不是完整的逐题真实历史行情案例库。
- 当前学习报告中的每日一图展示真实K线，但尚未实现图上逐点标注、缩放和多指标切换。
- 原有投资分析报告模板仍待完成彻底离线化；学习报告本身为自包含离线HTML。
