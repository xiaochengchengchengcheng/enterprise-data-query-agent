import unittest

from model_registry import ModelRegistry


class ModelRegistryTest(unittest.TestCase):
    def test_local_hashing_embedding_is_deterministic(self):
        registry = ModelRegistry()
        left = registry.embed(['销售收入'], 'local-hashing')[0]
        right = registry.embed(['销售收入'], 'local-hashing')[0]
        other = registry.embed(['员工数量'], 'local-hashing')[0]
        self.assertEqual(left, right)
        self.assertNotEqual(left, other)
        self.assertAlmostEqual(sum(item * item for item in left), 1.0, places=6)


if __name__ == '__main__':
    unittest.main()
