import pytest
from pydantic import ValidationError

from app.schemas import RefreshIn


def test_refresh_token_too_long_rejected():
    with pytest.raises(ValidationError):
        RefreshIn(refresh_token="x" * 257)


def test_refresh_token_normal_size_accepted():
    assert RefreshIn(refresh_token="x" * 43).refresh_token == "x" * 43
