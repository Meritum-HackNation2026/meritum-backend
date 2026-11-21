import pytest

from meritum_backend.sms.numbers import e164


@pytest.mark.parametrize(
    "raw",
    [
        "+48600700800",
        "+48 600 700 800",
        "600 700 800",
        "600-700-800",
        "0048600700800",
        "48600700800",
    ],
)
def test_polish_number_formats_become_one_e164(raw: str) -> None:
    assert e164(raw) == "+48600700800"


def test_foreign_number_keeps_its_country_code() -> None:
    assert e164("+44 20 7946 0958") == "+442079460958"
