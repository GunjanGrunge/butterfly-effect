import pytest

from discount import calculate_discount


@pytest.mark.parametrize("bad", [-0.01, -50, float("nan"), float("inf"), float("-inf")])
def test_invalid_totals_are_rejected(bad):
    with pytest.raises(ValueError):
        calculate_discount(bad)


def test_zero_total_is_zero():
    assert calculate_discount(0, "WELCOME25", "staff") == 0.0
