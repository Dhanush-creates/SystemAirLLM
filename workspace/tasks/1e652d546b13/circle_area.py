import math

def area_of_circle(radius):
    return math.pi * radius ** 2

# Unit test
import unittest

class TestCircleArea(unittest.TestCase):
    def test_area_of_circle(self):
        self.assertEqual(area_of_circle(1), math.pi)
        self.assertEqual(area_of_circle(0), 0)
        self.assertEqual(area_of_circle(2), 4 * math.pi)

if __name__ == '__main__':
    unittest.main()