import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import accounts

class AccountTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        a = accounts.password_hash('a-long-test-password', '00'*16)
        self.assertEqual(a, accounts.password_hash('a-long-test-password', '00'*16))
        self.assertNotEqual(a, accounts.password_hash('a-long-test-password', '11'*16))

    def test_calorie_goal_settings_are_validated_and_legacy_data_is_supported(self):
        base = {'logs': [], 'checkins': {}}
        self.assertTrue(accounts.valid_data(base))
        self.assertTrue(accounts.valid_data({**base, 'settings': {'calorieGoals': [{'day':'2026-10-21','calories':2200}]}}))
        for calories in (0, -1, 20001, True, '2200'):
            self.assertFalse(accounts.valid_data({**base, 'settings': {'calorieGoals': [{'day':'2026-10-21','calories':calories}]}}))

    def test_revision_prevents_stale_overwrite_and_preserves_other_user(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(accounts, 'DB', Path(directory)/'test.sqlite3'):
            with accounts.connect() as db:
                db.execute('INSERT INTO users(email,salt,password) VALUES(?,?,?)', ('a@example.invalid','salt','hash'))
                db.execute('INSERT INTO users(email,salt,password) VALUES(?,?,?)', ('b@example.invalid','salt','hash'))
                db.commit()
                first = db.execute('UPDATE users SET data=?,revision=revision+1 WHERE id=1 AND revision=0', ('{"logs":[],"checkins":{"today":{}}}',))
                self.assertEqual(first.rowcount, 1)
                stale = db.execute('UPDATE users SET data=?,revision=revision+1 WHERE id=1 AND revision=0', ('{}',))
                self.assertEqual(stale.rowcount, 0)
                self.assertEqual(json.loads(db.execute('SELECT data FROM users WHERE id=2').fetchone()[0]), {'logs':[], 'checkins':{}})

if __name__ == '__main__':
    unittest.main()
