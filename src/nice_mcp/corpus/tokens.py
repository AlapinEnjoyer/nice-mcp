"""Token counting used to keep corpus chunks within model context limits."""

from collections.abc import Callable
from typing import Protocol, cast


class _Tokenizer(Protocol):
    """The small tokenizer interface required for chunk sizing."""

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]: ...


def load_token_counter(model_id: str) -> Callable[[str], int]:
    """Load a model tokenizer and return a counter including special tokens."""
    try:
        from transformers import AutoTokenizer
    except ImportError as error:
        raise RuntimeError("model tokenization requires the 'neural' optional dependencies") from error

    tokenizer = cast(_Tokenizer, AutoTokenizer.from_pretrained(model_id))
    return lambda text: len(tokenizer.encode(text, add_special_tokens=True))
