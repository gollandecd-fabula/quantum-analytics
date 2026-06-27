import unittest
from decimal import Decimal

from quantum.domain.states import DataState, TypedValue


class TypedValueTests(unittest.TestCase):
    def test_valid_zero_is_not_empty(self):
        value = TypedValue.valid(Decimal("0.00"), value_type="decimal", unit="RUB")
        self.assertEqual(value.state, DataState.VALID)
        self.assertEqual(value.value, Decimal("0.00"))

    def test_empty_with_zero_is_rejected(self):
        with self.assertRaises(ValueError):
            TypedValue(
                state=DataState.EMPTY,
                value=Decimal("0.00"),
                value_type="decimal",
                reason_code="SOURCE_EMPTY",
            )

    def test_unavailable_requires_reason(self):
        with self.assertRaises(ValueError):
            TypedValue(
                state=DataState.UNAVAILABLE,
                value=None,
                value_type=None,
                reason_code=None,
            )

    def test_missing_factory_rejects_valid_state(self):
        with self.assertRaises(ValueError):
            TypedValue.missing(DataState.VALID, reason_code="INVALID_FACTORY_USE")


if __name__ == "__main__":
    unittest.main()
