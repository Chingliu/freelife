import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from course_content import build_course_html


class CourseContentTests(unittest.TestCase):
    def setUp(self):
        self.chart = {
            "full_dates": ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"],
            "full_ohlc": [
                [4.00, 4.02, 3.98, 4.04],
                [4.02, 4.01, 3.99, 4.03],
                [4.01, 4.05, 4.00, 4.06],
                [4.05, 4.03, 4.01, 4.07],
            ],
            "full_vols": [1.2, 1.0, 1.5, 1.1],
        }
        self.metrics = {"as_of": "2026-11-19", "snapshot": {"hqdate": "20261119"},
                        "moneyflow": {"cmf20": 0.012}}

    def test_all_six_chapters_render_with_real_values(self):
        page = build_course_html(self.chart, self.metrics)
        for title in ("K线基础", "成交量", "趋势分析", "日K/周K/月K多周期分析",
                      "技术指标", "量价关系综合应用"):
            self.assertIn(title, page)
        self.assertIn("4.050", page)
        self.assertIn("2026-11-19", page)
        self.assertIn("如果本次采集发生在交易时段", page)

    def test_charts_teach_by_direct_annotations(self):
        page = build_course_html(self.chart, self.metrics)
        # Labels must point to the visual feature, not merely describe it in prose.
        for marker in ("上影线", "实体", "下影线", "最新量柱", "MA5", "MA20",
                       "MA60", "周K：看中期波段结构", "月K：看长期大方向",
                       "弱势参考 30", "强势参考 70", "零轴"):
            self.assertIn(marker, page)
        self.assertIn("<polyline points=", page)  # actual moving-average curves

    def test_missing_data_does_not_fabricate_examples(self):
        page = build_course_html({}, self.metrics)
        self.assertIn("没有可用的真实日线数组", page)
        self.assertNotIn("4.050", page)


if __name__ == "__main__":
    unittest.main()
