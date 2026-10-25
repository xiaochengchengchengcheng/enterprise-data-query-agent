import os
import tempfile
import unittest

from api_key_manager import APIKeyManager


class APIKeyManagerTest(unittest.TestCase):
    def test_create_verify_scope_and_revoke(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = APIKeyManager(os.path.join(directory, 'keys.sqlite3'))
            token, metadata = manager.create_key('analyst', ['analysis'], 1)
            self.assertTrue(token.startswith('eda_'))
            self.assertIsNotNone(manager.verify(token, 'analysis'))
            self.assertIsNone(manager.verify(token, 'admin'))
            self.assertTrue(manager.revoke(metadata['id']))
            self.assertIsNone(manager.verify(token, 'analysis'))


if __name__ == '__main__':
    unittest.main()
