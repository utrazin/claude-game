import unittest

from lib import ModelBuilder, Placement


def rotated_arm():
    b = ModelBuilder("t", require_integer_dimensions=False)
    b.add_group("root")
    b.add_transform_group("arm", "root", pivot=(0, 10, 0), rotation=(0, 0, 90))
    b.add_box("bx", "arm", size=(1, 1, 1), at=(5, 10, 0))
    return b


class SocketInRotatedGroupTests(unittest.TestCase):
    def test_a_socket_given_numbers_moves_with_its_group_like_a_box_does(self):
        b = rotated_arm()
        b.add_socket("s", "arm", at=(5, 10, 0), forward=(1, 0, 0), up=(0, 1, 0))
        box = b.get_anchor("bx", "center")
        socket = b.get_socket("s")
        for got, want in zip(socket.origin, box):
            self.assertAlmostEqual(got, want, places=6)
        for got, want in zip(socket.forward, (0, 1, 0)):
            self.assertAlmostEqual(got, want, places=6)

    def test_placement_at_the_socket_lands_on_the_posed_position(self):
        b = rotated_arm()
        b.add_socket("s", "arm", at=(5, 10, 0), forward=(1, 0, 0), up=(0, 1, 0))
        b.add_cylinder("c", "root", radius=1, height=1, placement=Placement.at("socket:s"))
        for got, want in zip(b.get_anchor("c", "center"), b.get_anchor("bx", "center")):
            self.assertAlmostEqual(got, want, places=6)

    def test_an_unrotated_group_is_unchanged(self):
        b = ModelBuilder("t", require_integer_dimensions=False)
        b.add_group("root")
        b.add_transform_group("arm", "root", pivot=(0, 10, 0))
        b.add_socket("s", "arm", at=(5, 10, 0), forward=(1, 0, 0), up=(0, 1, 0))
        self.assertEqual(tuple(round(v, 6) for v in b.get_socket("s").origin), (5, 10, 0))


if __name__ == "__main__":
    unittest.main()
