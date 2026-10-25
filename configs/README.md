# Example configurations

Each file is a full `RenderOptions` set; use them as a reference for the CLI flags or pass the JSON
straight to the notebook/API.

| file | what it demonstrates |
|---|---|
| `quick-draft-16x9.json` | fastest useful render, one language, one format |
| `bilingual-both-formats.json` | all four language × format combinations in one run |
| `urdu-vertical-story.json` | Urdu-only 9:16 with captions on and a 60 s target |
| `no-character-talking-head.json` | same engine with the presenter disabled (still one character rule, just absent) |
| `notes-augmented.json` | attaching your own facts via `notes` (must be provided in every language) |

In Python:

```python
import json
from ckd.content.options import RenderOptions
from ckd.pipeline.run import Pipeline

opts = RenderOptions.from_dict(json.load(open("configs/bilingual-both-formats.json")))
result = Pipeline(opts, root=".").run()
print(result["videos"])
```

Note: `draft` quality renders at 480p with supersample 1 — good for checking timing and layout, not for
publishing. `high` is 1080p and roughly 2.5× slower than `standard`.
