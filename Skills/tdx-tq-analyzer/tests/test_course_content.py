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
        self.assertIn("最新日K/当周K/当月K可能尚未完成", page)

    def test_missing_data_does_not_fabricate_examples(self):
        page = build_course_html({}, self.metrics)
        self.assertIn("没有可用的真实日线数组", page)
        self.assertNotIn("4.050", page)


if __name__ == "__main__":
    unittest.main()
