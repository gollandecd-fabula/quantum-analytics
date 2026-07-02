from __future__ import annotations

from ._expression_eager import _validate_operation_signature
from ._expression_lazy import evaluate_expression

__all__ = ["evaluate_expression", "_validate_operation_signature"]
