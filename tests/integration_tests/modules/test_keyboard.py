import pytest

USER_DATA = """\
#cloud-config
keyboard:
    layout: de
    model: pc105
    variant: nodeadkeys
    options: compose:rwin
"""


class TestKeyboard:
    @pytest.mark.user_data(USER_DATA)
    def test_keyboard(self, client):
        lc = client.execute("localectl")
        assert "X11 Layout: de" in lc
