import unittest
import math
from circle_area import area_of_circle

class TestCircleArea(unittest.TestCase):
    def test_area_of_circle(self):
        self.assertEqual(area_of_circle(1), math.pi)
        self.assertEqual(area_of_circle(0), 0)
        self.assertEqual(area_of_circle(2), 4 * math.pi)

if __name__ == '__main__':
    unittest.main()