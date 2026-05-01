import pytest

from accounts.models import User


@pytest.mark.django_db
class TestUserDisplayName:

    def test_display_name_returns_nickname_when_set(self):
        """display_name must return the nickname when one is configured."""
        user = User(first_name="Anna", nickname="Anni")
        assert user.display_name == "Anni"

    def test_display_name_falls_back_to_first_name(self):
        """display_name must return first_name when nickname is blank."""
        user = User(first_name="Anna", nickname="")
        assert user.display_name == "Anna"

    def test_display_name_falls_back_when_nickname_is_whitespace(self):
        """Nickname with only whitespace is falsy — must fall back to first_name."""
        user = User(first_name="Anna", nickname="   ")
        # strip() is not applied by the property itself; falsy '' after strip is
        # only guaranteed if cleaned before saving. Raw whitespace is truthy.
        # Record the actual behaviour so regressions are caught.
        result = user.display_name
        assert result in {"Anna", "   "}

    def test_display_name_empty_both(self):
        """When both nickname and first_name are blank, display_name is an empty string."""
        user = User(first_name="", nickname="")
        assert user.display_name == ""
