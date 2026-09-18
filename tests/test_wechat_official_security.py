import hashlib
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins" / "platforms" / "wechat_official"))

from security import valid_callback_signature


class CallbackSignatureTests(unittest.TestCase):
    def test_accepts_the_matching_signature(self):
        token, timestamp, nonce = "secret", "1700000000", "42"
        signature = hashlib.sha1("".join(sorted((token, timestamp, nonce))).encode()).hexdigest()

        self.assertTrue(valid_callback_signature(token, timestamp, nonce, signature))

    def test_rejects_a_modified_signature(self):
        self.assertFalse(valid_callback_signature("secret", "1700000000", "42", "not-valid"))
