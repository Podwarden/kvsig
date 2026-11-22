# kvsig for Python

Keyed, content-derived ids for LLM chat conversations. This is the reference
implementation of the [kvsig specification](https://github.com/Podwarden/kvsig/blob/main/SPEC.md)
(`kvsig/1`, draft 0.1): pure Python, no third-party dependencies, typed.

A gateway or router that sees a stream of stateless chat requests can use it to
tell which conversation each request belongs to, which prefix it shares with an
earlier request, and whether the system prompt or the tools changed, the same
way in OpenAI Chat Completions, OpenAI Responses and Anthropic Messages.

## Install

```bash
pip install kvsig
```

Python 3.10 or later.

## Quickstart

```python
from kvsig import Key, canonicalize, ids

key = Key.generate(epoch=1)  # one per deployment; keep it secret and keep it
body = {
    "model": "m",
    "messages": [
        {"role": "system", "content": "You answer geography questions."},
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "Paris."},
        {"role": "user", "content": "And Spain?"},
    ],
}

canon = canonicalize(body, "openai.chat")  # None means "this request gets no ids"
if canon is not None:
    i = ids(canon, key)
    i.conv  # conversation id: stable across turns, reminders, dates and tool changes
    i.nodes[-1]  # id of the whole prefix, like a git commit
    i.sys, i.tools  # the two halves of the head: which one changed?
```

The same conversation sent as `"anthropic.messages"` or `"openai.responses"`
gives the same ids. Hostile or oversized input never raises; it gives `None`.

To check your install against the published test vectors, use the published
test key (epoch 0) on the vector
[`openai.chat/conv-base`](https://github.com/Podwarden/kvsig/blob/main/vectors/v1/openai.chat/conv-base.json):

```python
import json
from kvsig import TEST_KEY, canonicalize, ids

v = json.load(open("vectors/v1/openai.chat/conv-base.json"))
i = ids(canonicalize(v["input"], v["dialect"]), TEST_KEY)
assert i.conv == v["expect"]["keys"]["0"]["conv"]  # "00fdd9bdfb7d14a82cb5d7d4d70ac60046"
```

## What 0.1 guarantees

- For the spec label `kvsig/1` and the loose profile `loose/1` (the default),
  canonical bytes and ids are pinned by the
  [`vectors/v1`](https://github.com/Podwarden/kvsig/tree/main/vectors) test
  vectors. No later release changes them; a change ships under a new label or
  profile version instead.
- `LOOSE_V2` (`loose/2`, decision 0005) is included but **experimental**: it is
  not covered by the vectors yet and its ids may change until its decision is
  accepted.
- The full policy is in the [specification](https://github.com/Podwarden/kvsig/blob/main/SPEC.md#versioning-and-compatibility).

## Learn more

- [Reading the ids](https://github.com/Podwarden/kvsig/blob/main/docs/reading-the-ids.md):
  what each id identifies, and how to tell what changed between two requests.
- [Conformance runner](https://github.com/Podwarden/kvsig/tree/main/conformance):
  check any implementation, in any language, against the vectors.
- [Changelog](https://github.com/Podwarden/kvsig/blob/main/CHANGELOG.md).

## Development

From `python/` in a checkout:

```bash
uv run --with pytest pytest -q
uv run --with ruff ruff check . && uv run --with ruff ruff format --check .
python ../conformance/run.py -- python ../conformance/adapters/python_adapter.py
```

## Licence

Apache-2.0. The specification text is licensed separately under CC BY 4.0; see
[NOTICE](https://github.com/Podwarden/kvsig/blob/main/NOTICE).
