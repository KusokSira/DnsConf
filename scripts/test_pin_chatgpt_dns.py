import copy
import unittest

from pin_chatgpt_dns import NextDNS, apply_pins


class FakeAPI:
    def __init__(self, rows, fail_add=False, uncertain_add=False):
        self.data = copy.deepcopy(rows)
        self.writes = 0
        self.fail_add = fail_add
        self.uncertain_add = uncertain_add

    def rows(self):
        return copy.deepcopy(self.data)

    def remove(self, row):
        self.writes += 1
        self.data = [r for r in self.data if r["id"] != row["id"]]

    def add(self, name, content):
        self.writes += 1
        if self.fail_add:
            self.fail_add = False
            raise RuntimeError("Simulated failed write")
        self.data.append({"id": str(self.writes), "name": name, "content": content})
        if self.uncertain_add:
            self.uncertain_add = False
            raise RuntimeError("Simulated lost response after successful write")


def row(identifier, name, content):
    return {"id": identifier, "name": name, "content": content}


class PinTests(unittest.TestCase):
    def test_preserves_other_records_and_repeated_run_is_noop(self):
        unrelated = row("unrelated", "example.com", "192.0.2.1")
        api = FakeAPI([unrelated, row("old", "chatgpt.com", "192.0.2.2")])
        apply_pins(api)
        self.assertIn(unrelated, api.data)
        writes = api.writes
        apply_pins(api)
        self.assertEqual(api.writes, writes)

    def test_reuses_correct_record_and_removes_duplicate(self):
        api = FakeAPI([row("good", "chatgpt.com", "193.233.112.68"), row("bad", "chatgpt.com", "192.0.2.2")])
        apply_pins(api, {"chatgpt.com": "193.233.112.68"})
        self.assertEqual([r["id"] for r in api.data], ["good"])

    def test_failed_add_restores_previous_record(self):
        api = FakeAPI([row("old", "chatgpt.com", "192.0.2.2")], fail_add=True)
        with self.assertRaises(RuntimeError):
            apply_pins(api, {"chatgpt.com": "193.233.112.68"})
        self.assertEqual([r["content"] for r in api.data], ["192.0.2.2"])

    def test_lost_success_response_does_not_create_duplicates(self):
        api = FakeAPI([row("old", "chatgpt.com", "192.0.2.2")], uncertain_add=True)
        apply_pins(api, {"chatgpt.com": "193.233.112.68"})
        self.assertEqual([r["content"] for r in api.data], ["193.233.112.68"])

    def test_rejects_multiple_profiles(self):
        for profile, key in [("abc123,aaaaaa", "fake"), ("abc123", "fake,other"), ("abc123", "")]:
            with self.assertRaises(ValueError):
                NextDNS(profile, key)


if __name__ == "__main__":
    unittest.main()
