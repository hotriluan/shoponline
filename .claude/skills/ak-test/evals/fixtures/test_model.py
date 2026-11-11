import unittest
from model import authorized, download, quota
class ContractTests(unittest.TestCase):
    def test_owner(self): self.assertTrue(authorized({"tenant":"a"}, "a"))
    def test_owner_duplicate(self): self.assertEqual(authorized({"tenant":"a"}, "a"), True)
    def test_anonymous(self): self.assertFalse(authorized(None,"a"))
    def test_cross_tenant(self): self.assertFalse(authorized({"tenant":"a"},"b"))
    def test_csv(self): self.assertEqual(download(["a","b"],"csv"),"a,b")
    def test_quota(self): self.assertTrue(quota(3)); self.assertFalse(quota(4))
if __name__ == "__main__": unittest.main()
