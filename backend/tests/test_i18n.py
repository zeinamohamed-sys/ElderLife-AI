import unittest
from app import i18n
from app.risk import assess_rules

BASE = dict(checkin_delay_min=5, checkin_responded=True, checkin_usual_min=8, activity_ratio=1.0,
            fall=False, fall_answered=False, fall_age_s=0, verify_s=60, sos=False, missed_reminders=0)

class TranslationTests(unittest.TestCase):
    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(set(i18n.EN), set(i18n.AR))

    def test_every_key_is_actually_translated(self):
        # Arabic texts must really be Arabic; the only allowed Latin words are product/event names.
        for key, ar in i18n.AR.items():
            cleaned = ar
            for word in ("ElderLife", "activity", "fall", "ok", "sos"):
                cleaned = cleaned.replace(word, "")
            cleaned = cleaned.replace("{pct}", "").replace("{n}", "").replace("{name}", "").replace("{level}", "").replace("{reasons}", "").replace("{contact}", "")
            latin = [w for w in cleaned.split() if any(c.isascii() and c.isalpha() for c in w)]
            self.assertEqual(latin, [], f"{key} is not translated: {ar}")

    def test_negotiate(self):
        self.assertEqual(i18n.negotiate("ar-EG,ar;q=0.9,en;q=0.8"), "ar")
        self.assertEqual(i18n.negotiate("en-GB"), "en")
        self.assertEqual(i18n.negotiate("fr"), i18n.DEFAULT_LANG)
        self.assertEqual(i18n.negotiate(None), i18n.DEFAULT_LANG)

    def test_reasons_are_stored_as_keys_and_rendered(self):
        r = assess_rules({**BASE, "fall": True, "fall_age_s": 90, "missed_reminders": 3, "activity_ratio": 0.2})
        self.assertEqual(len(r["reasons"]), len(r["reason_codes"]))
        payload = i18n.reasons_to_json(r["reason_codes"])
        self.assertIn("Fall detected", i18n.reasons_text(payload, "en"))
        self.assertIn("تم رصد سقطة", i18n.reasons_text(payload, "ar"))
        self.assertIn("3", i18n.reasons_text(payload, "ar"))

    def test_old_plain_english_rows_still_work(self):
        self.assertEqual(i18n.reasons_text("Fall detected", "ar"), "Fall detected")
        self.assertEqual(i18n.reasons_text(None, "ar"), "")

    def test_errors_are_translated(self):
        self.assertEqual(i18n.translate_error("Wrong code", "ar"), "الرمز غير صحيح")
        self.assertEqual(i18n.translate_error("Some new error", "ar"), "Some new error")

    def test_notification_is_rendered_per_reader(self):
        raw = i18n.reasons_to_json([{"key": "reason.fall_detected", "params": {}}])
        import json
        note = json.dumps({"key": "notif.risk", "params": {"name": "Hoda", "level": "High", "reason_codes": i18n.load_reasons(raw)}})
        self.assertEqual(i18n.render_notification(note, "en"), "Hoda: High risk. Fall detected")
        self.assertEqual(i18n.render_notification(note, "ar"), "Hoda: مستوى الخطر مرتفع. تم رصد سقطة")
        legacy = "Hoda: High risk. Fall detected"
        self.assertEqual(i18n.render_notification(legacy, "ar"), legacy)

    def test_emergency_notification_fills_missing_contact(self):
        import json
        note = json.dumps({"key": "notif.emergency", "params": {"name": "Samir", "contact": "", "reason_codes": []}})
        self.assertIn("not set", i18n.render_notification(note, "en"))
        self.assertIn("غير محدد", i18n.render_notification(note, "ar"))

if __name__ == "__main__":
    unittest.main()
