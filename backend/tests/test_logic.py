import unittest
from app.risk import assess, assess_rules, ml_enabled
from app.vision import classify, classify_auto, sample_pose

BASE = dict(checkin_delay_min=5, checkin_responded=True, checkin_usual_min=8, activity_ratio=1.0,
            fall=False, fall_answered=False, fall_age_s=0, verify_s=60, sos=False, missed_reminders=0)
def risk(**kw): return assess_rules({**BASE, **kw})
def model_risk(**kw): return assess({**BASE, **kw, 'hour': 14, 'age': 78, 'fall_conf': 0.9})

class RiskTests(unittest.TestCase):
    def test_normal(self): self.assertEqual(risk()["level"], "Normal")
    def test_fall_waits_for_answer(self):
        r = risk(fall=True, fall_age_s=10); self.assertEqual(r["level"], "Medium")
    def test_fall_unanswered_is_high(self): self.assertEqual(risk(fall=True, fall_age_s=90)["level"], "High")
    def test_fall_answered_is_low(self): self.assertEqual(risk(fall=True, fall_answered=True)["level"], "Low")
    def test_everything_wrong_is_critical(self):
        r = risk(fall=True, fall_age_s=90, checkin_responded=False, checkin_delay_min=200, activity_ratio=.2)
        self.assertEqual(r["level"], "Critical"); self.assertIn("No response after fall", r["reasons"])
    def test_sos_is_critical(self): self.assertEqual(risk(sos=True)["level"], "Critical")
    def test_personal_late_threshold(self):
        self.assertEqual(risk(checkin_responded=False, checkin_delay_min=25)["level"], "Normal")
        self.assertEqual(risk(checkin_responded=False, checkin_delay_min=40)["level"], "Low")

class ModelTests(unittest.TestCase):
    def test_model_is_loaded(self): self.assertTrue(ml_enabled())
    def test_normal_stays_normal(self): self.assertEqual(model_risk()["level"], "Normal")
    def test_sos_cannot_be_hidden(self): self.assertEqual(model_risk(sos=True)["level"], "Critical")
    def test_unanswered_fall_is_at_least_high(self):
        self.assertIn(model_risk(fall=True, fall_age_s=120)["level"], ("High", "Critical"))
    def test_fall_inside_verification_window_is_not_an_alert(self):
        self.assertNotIn(model_risk(fall=True, fall_age_s=10)["level"], ("High", "Critical"))
    def test_night_inactivity_is_not_an_alert(self):
        r = assess({**BASE, "hour": 3, "age": 78, "activity_ratio": 0.3}); self.assertIn(r["level"], ("Normal", "Low"))
    def test_explains_itself(self):
        m = model_risk(fall=True, fall_age_s=120)["model"]; self.assertTrue(m["top_factors"]); self.assertGreater(m["probability"], 0.3)

class VisionTests(unittest.TestCase):
    def test_static_poses(self):
        for kind in ("standing", "sitting", "bending", "lying"):
            self.assertEqual(classify(sample_pose(kind))[0], kind, kind)
    def test_walking(self):
        self.assertEqual(classify(sample_pose("standing", .55), sample_pose("standing", .50), 0.5)[0], "walking")
    def test_fall(self):
        act, conf = classify(sample_pose("falling"), sample_pose("standing"), 0.5)
        self.assertEqual(act, "falling"); self.assertGreaterEqual(conf, 0.6)

class PoseModelTests(unittest.TestCase):
    def test_trained_model_on_canned_poses(self):
        for kind in ("standing", "sitting", "lying"):
            act, conf, src = classify_auto(sample_pose(kind)); self.assertEqual(src, "ml"); self.assertEqual(act, kind, kind)
    def test_trained_model_detects_fall(self):
        self.assertEqual(classify_auto(sample_pose("falling"), sample_pose("standing"), 0.5)[0], "falling")

if __name__ == "__main__": unittest.main()
