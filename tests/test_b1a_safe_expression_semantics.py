import unittest

Signature = tuple[str, str, str | None]


class SemanticMismatch(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require_same(left: Signature, right: Signature) -> None:
    if left[0] != right[0]:
        raise SemanticMismatch("EXPRESSION_TYPE_MISMATCH")
    if left[1] != right[1]:
        raise SemanticMismatch("EXPRESSION_UNIT_MISMATCH")
    if left[2] != right[2]:
        raise SemanticMismatch("EXPRESSION_CURRENCY_MISMATCH")


def derive_binary(operator: str, left: Signature, right: Signature) -> Signature:
    if operator in {"ADD", "SUBTRACT", "MIN", "MAX"}:
        require_same(left, right)
        return left
    if operator in {
        "EQUAL",
        "LESS_THAN",
        "LESS_OR_EQUAL",
        "GREATER_THAN",
        "GREATER_OR_EQUAL",
    }:
        require_same(left, right)
        return "BOOLEAN", "BOOLEAN", None
    if operator == "MULTIPLY":
        if left[0] == "MONEY" and right in {
            ("DECIMAL", "DIMENSIONLESS", None),
            ("RATE", "RATE", None),
        }:
            return left
        if right[0] == "MONEY" and left in {
            ("DECIMAL", "DIMENSIONLESS", None),
            ("RATE", "RATE", None),
        }:
            return right
        if left == right == ("DECIMAL", "DIMENSIONLESS", None):
            return left
        raise SemanticMismatch("EXPRESSION_TYPE_MISMATCH")
    if operator == "DIVIDE":
        if left[0] == right[0] == "MONEY":
            require_same(left, right)
            return "DECIMAL", "DIMENSIONLESS", None
        if left[0] == "MONEY" and right == ("DECIMAL", "DIMENSIONLESS", None):
            return left
        if left == right == ("DECIMAL", "DIMENSIONLESS", None):
            return left
        raise SemanticMismatch("EXPRESSION_TYPE_MISMATCH")
    raise SemanticMismatch("EXPRESSION_OPERATOR_FORBIDDEN")


def validate_binary(
    operator: str,
    declared: Signature,
    left: Signature,
    right: Signature,
) -> Signature:
    derived = derive_binary(operator, left, right)
    require_same(declared, derived)
    return derived


class B1aSafeExpressionSemanticTests(unittest.TestCase):
    def test_binary_compatibility_is_fail_closed(self) -> None:
        eur = ("MONEY", "MONEY", "EUR")
        usd = ("MONEY", "MONEY", "USD")
        rate = ("RATE", "RATE", None)
        decimal = ("DECIMAL", "DIMENSIONLESS", None)
        items = ("INTEGER", "ITEM", None)
        orders = ("INTEGER", "ORDER", None)
        boolean = ("BOOLEAN", "BOOLEAN", None)

        self.assertEqual(validate_binary("SUBTRACT", eur, eur, eur), eur)
        self.assertEqual(validate_binary("MULTIPLY", eur, eur, rate), eur)
        self.assertEqual(validate_binary("DIVIDE", decimal, eur, eur), decimal)
        self.assertEqual(validate_binary("LESS_THAN", boolean, items, items), boolean)

        vectors = [
            ("SUBTRACT", eur, eur, usd, "EXPRESSION_CURRENCY_MISMATCH"),
            ("SUBTRACT", eur, eur, rate, "EXPRESSION_TYPE_MISMATCH"),
            ("LESS_THAN", boolean, items, orders, "EXPRESSION_UNIT_MISMATCH"),
            ("MULTIPLY", eur, eur, items, "EXPRESSION_TYPE_MISMATCH"),
            ("SUBTRACT", usd, eur, eur, "EXPRESSION_CURRENCY_MISMATCH"),
        ]
        for operator, declared, left, right, diagnostic in vectors:
            with self.subTest(diagnostic=diagnostic), self.assertRaises(
                SemanticMismatch
            ) as raised:
                validate_binary(operator, declared, left, right)
            self.assertEqual(raised.exception.code, diagnostic)


if __name__ == "__main__":
    unittest.main()
