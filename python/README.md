# kvsig for Python (reference implementation)

Pure-Python reference implementation of [kvsig](../SPEC.md), with no
third-party dependencies. **Not released yet**, and ids may change in 0.x.

```python
from kvsig import Key, canonicalize, ids

key = Key.generate(epoch=1)  # keep it: every id depends on it
canon = canonicalize(request_body, "anthropic.messages")  # None means "no ids"
if canon is not None:
    i = ids(canon, key)
    i.conv  # conversation id: stable across turns, reminders, dates and tool changes
    i.nodes[-1]  # id of the whole prefix, like a git commit
    i.sys, i.tools  # the two halves of the head: which one changed?
```

Implemented so far: the `openai.chat`, `anthropic.messages` and `openai.responses`
dialects (one conversation gives the same ids in all three), the `loose/1`
profile, keyed ids, key rings for rotation, and a bounded `IdCache`. Legacy
`openai.completions`, the test vectors and the Rust core come next.

Development:

```bash
uv run --with pytest pytest -q
uv run --with ruff ruff check . && uv run --with ruff ruff format --check .
```

What each id means, and how to compare two requests: [Reading the ids](../docs/reading-the-ids.md).
