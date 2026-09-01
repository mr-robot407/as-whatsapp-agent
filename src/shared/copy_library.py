"""Load `config/copy_library.json` and render {substitutions}.

Verbatim message bodies — never generate copy. `style_guard.assert_clean()`
must still be called at the wa_client layer as belt-and-braces.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(
    os.environ.get(
        "CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config")
    )
) / "copy_library.json"

_SUB = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@lru_cache(maxsize=1)
def _registry() -> dict:
    with open(_CONFIG_PATH) as fh:
        return json.load(fh)


def get(state_id: str, key: str = "body") -> str:
    """Return copy for state_id at the given key (default `body`).

    S1.18.step_b, E.SUB.step_a, S1.14.GATE, etc. use compound state ids —
    those with a dot at the top level are looked up whole, then descend by
    dot for nested keys.
    """
    reg = _registry()
    if state_id in reg and key in reg[state_id]:
        return reg[state_id][key]
    raise KeyError(f"copy: state_id={state_id!r} key={key!r} not found")


def render(state_id: str, subs: dict[str, str] | None = None, key: str = "body") -> str:
    """Render body with {name} → subs[name]. Raises if a placeholder is missing."""
    template = get(state_id, key=key)
    subs = subs or {}
    missing: list[str] = []

    def _resolve(match: re.Match) -> str:
        name = match.group(1)
        if name not in subs:
            missing.append(name)
            return match.group(0)
        return str(subs[name])

    rendered = _SUB.sub(_resolve, template)
    if missing:
        raise ValueError(
            f"copy.render({state_id!r}, key={key!r}) — unfilled substitutions: {missing}"
        )
    return rendered
