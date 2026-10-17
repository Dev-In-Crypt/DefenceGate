"""Entity resolution for the networks layer: one cascade, every decision stored with its
method and confidence. See cascade.py for the stages and evaluate.py for the yardstick."""

from .cascade import Resolution, resolve  # noqa: F401
from .names import key_of  # noqa: F401
