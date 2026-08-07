"""Strict YAML loading helpers."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any, cast

import yaml


class _UniqueKeySafeLoader(yaml.SafeLoader):  # type: ignore[misc]
    """SafeLoader variant that rejects duplicate mapping keys."""

    def construct_mapping(
        self,
        node: Any,
        deep: bool = False,
    ) -> dict[Any, Any]:
        seen: set[Hashable] = set()

        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue

            key = self.construct_object(key_node, deep=False)
            if isinstance(key, Hashable):
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key {key!r}",
                        key_node.start_mark,
                    )
                seen.add(key)

        return cast(dict[Any, Any], super().construct_mapping(node, deep=deep))


def safe_load_yaml(text: str) -> object:
    """Safely parse YAML while rejecting duplicate mapping keys."""

    loader = _UniqueKeySafeLoader(text)
    try:
        return cast(object, loader.get_single_data())
    finally:
        loader.dispose()
