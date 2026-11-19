import json, tempfile, unittest
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from learning_engine import load_curriculum, fresh_state, build_daily_plan, record_result

class LearningTests(unittest.TestCase):
    def test_curriculum_ids_unique_and_six_chapters(self):
        c=load_curriculum(); self.assertEqual(len(c["chapters"]),6)
        ids=[x[0] for ch in c["chapters"] for x in ch["lessons"]]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertGreaterEqual(len([x for ch in c["chapters"] if ch["status"]=="mvp" for x in ch["lessons"]]),20)
    def test_plan_is_deterministic(self):
        c=load_curriculum(); s=fresh_state(); d=date(2026,11,19)
        self.assertEqual(build_daily_plan(c,s,d),build_daily_plan(c,s,d))
    def test_review_due_after_record(self):
        s=fresh_state(); p=record_result(s,"K001",3,3,5,date(2026,11,19))
        self.assertEqual(p["due_date"],"2026-11-20")
        self.assertEqual(len(s["reviews"]),1)
if __name__=="__main__": unittest.main()
