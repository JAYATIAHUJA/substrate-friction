from mod_a import Widget


def test_render_positive():
    assert Widget().render(3) == 3
