# kvsig for Python (reference implementation)

Pure-Python reference implementation of [kvsig](../SPEC.md), with no
third-party dependencies. **Not released yet**, and ids may change in 0.x.

```python
from kvsig import Key, canonicalize, ids

key = Key.generate(epoch=1)  # keep it: every id depends on it
canon = canonicalize(request_body)  # an OpenAI chat body; None means "no ids"
if canon is not None:
    i = ids(canon, key)
    i.conv  # conversation id: stable across turns, reminders and dates
    i.nodes[-1]  # id of the whole prefix, like a git commit
```

Implemented so far: the `openai.chat` dialect, the `loose/1` profile, keyed ids,
key rings for rotation, and a bounded `IdCache`. The other dialects
(`openai.responses`, `anthropic.messages`, `openai.completions`), the test
vectors and the Rust core come next.

Development:

```bash
uv run --with pytest pytest -q
uv run --with ruff ruff check . && uv run --with ruff ruff format --check .
```
