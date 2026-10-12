# Squint

**A browser agent that works on your screen without seeing your secrets.**

Vision-based browser agents send screenshots of your tabs to a model. That means your face, card number and ID go with them. Squint puts a privacy layer in between: sensitive regions are detected and blacked out **on your device**, the model only ever receives the redacted image, and when it needs one of your details it writes a placeholder such as `{{card}}` that your machine fills in locally.

Built for Banana Hacks 2026.

## How it works

```
 your screen
     │  raw pixels (never leave the machine)
     ▼
┌─────────────────────── on your device ───────────────────────┐
│ capture → OCR + regex → face detection → DOM hints           │
│        → solid-fill redaction + numbered regions [3:card]    │
└──────────────────────────────┬───────────────────────────────┘
                               │ redacted PNG + region ids/types/positions
                               ▼
                   FastAPI server → Groq-hosted vision model
                               │ one action: click E2 / type "{{card}}" into [3]
                               ▼
┌─────────────────────── on your device ───────────────────────┐
│ executor: click / type; {{placeholders}} filled from a       │
│ local profile, so real values never reach the server         │
└──────────────────────────────────────────────────────────────┘
```

1. **Detect locally.** Tesseract reads the page at 2x upscale. Regexes run on *joined* lines, because OCR splits `4111 1111 1111 1111` into four boxes. MediaPipe BlazeFace finds faces on overlapping tiles. Digits that aren't sensitive (expiry dates, order numbers) are left alone.
2. **Redact locally.** Pixels are overwritten with a solid fill, not blurred, so nothing can be recovered. Each region is numbered and labelled (`[3:card]`).
3. **Ask the model.** The server receives the redacted image, a list of region ids, types and positions, and the task text. The model returns one action per step. Clickable elements are outlined and numbered `E1`, `E2`, ... on the screenshot, so it picks a number instead of guessing pixel coordinates.
4. **Act locally.** The executor clicks and types. Placeholders are resolved on your machine, and the action history sent back to the server contains placeholders only.

### What leaves your device

| Sent to the server | Never sent |
|---|---|
| Redacted screenshot (PNG) | The original screenshot |
| Region ids, types and positions (e.g. `[3] card at x,y,w,h`) | Any detected text or value |
| Task text and a placeholder-only action history | Resolved placeholder values |

The task text is sent as written, so don't put personal data in it. Use placeholders.

## Results

Synthetic benchmark: 200 generated checkout and receipt screenshots with randomised fonts, themes, zoom and layouts, scored in **pixel-only mode** (no DOM hints) on a laptop CPU. A detection counts at IoU ≥ 0.5; faces count when the detector box lies inside the photo frame, because the detector boxes facial features while the ground truth boxes the whole image. "Area covered" is the share of ground-truth boxes with at least 90% of their pixels redacted, whatever the label.

| Type | n | Recall | Precision | Area covered |
|---|---|---|---|---|
| Email | 169 | 92.3% | 100% | 92.3% |
| Phone | 200 | 99.5% | 100% | 98.0% |
| Card | 200 | 97.0% | 100% | 92.0% |
| Aadhaar | 67 | 100% | 97.1% | 97.0% |
| Address | 200 | 99.5% | 100% | 99.5% |
| **Face** | 163 | **47.9%** | **74.3%** | **36.8%** |

The five structured types average **97.7% recall at 99.4% precision** in about **0.53 s per screenshot**. Faces are the weak spot.

### Ablations

**OCR scale** (mean over email, phone, card, Aadhaar, address):

| Scale | Recall | Precision | Total latency |
|---|---|---|---|
| 1.0x | 96.7% | 97.2% | 295 ms |
| **2.0x** | **97.7%** | **99.4%** | 527 ms |
| 3.0x | 96.3% | 98.9% | 798 ms |

1x is 44% faster but loses about 6 points of phone recall. 3x costs more and is no more accurate. 2x is the default.

**Confidence threshold** (scale 2x): recall holds at 97.7% with no threshold, 95.9% at 0.5, 93.7% at 0.7, then drops to 72.3% at 0.8. Junk boxes (redactions that hide nothing sensitive) are 2.4% with no threshold and 0% from 0.6 up. Squint redacts with no threshold, because a missed secret costs more than an extra black box.

**Face tile size** (20-image subset, not re-run on all 200): 192 px tiles found every photo of 96 px and up; 256 px was worse and 128 px was much worse.

## Limitations

- **Faces:** only about 48% of faces are redacted correctly from pixels alone, and only 37% are fully covered. BlazeFace is built for large faces, and small avatars (under about 96 px) are often missed.
- **Names can't be found by pattern**, so in pixel-only mode they stay visible. DOM-hint mode covers them.
- **The benchmark is synthetic** and cleaner than real sites. The address pattern is tuned to the generated format, so expect lower numbers in the wild.
- **Region types and positions are visible to the server.** It can tell that a card field exists, just not what is in it.
- Coordinates and clicks are only tested in Chromium via Playwright. There is no browser extension yet.

## Quickstart

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and the Tesseract binary.

```bash
# system dependency
brew install tesseract            # macOS. On Ubuntu: sudo apt install tesseract-ocr

# python dependencies and browser
uv sync
uv run playwright install chromium
```

Create a `.env` in the repo root:

```
GROQ_API_KEY=gsk_...
SQUINT_MODEL=qwen/qwen3.8-27b
```

`SQUINT_MODEL` must be a vision-capable model on Groq. Model names change, so check <https://console.groq.com/docs/vision> if you get `model_not_found`.

The face model (about 200 KB) downloads to `models/` on first run, so the first run needs internet.

The mock checkout page shows a profile photo. Put any face image you have the rights to use in `mock_site/static/` (see the `<img src>` in `checkout.html` for the expected filename).

## Run the demo

Four terminals, all from the repo root:

```bash
# 1. mock checkout site
cd mock_site && uv run python -m http.server 8000

# 2. server (receives redacted images only)
uv run uvicorn squint.server.main:app --port 9000 --reload

# 3. local demo app (runs the agent and serves the UI)
uv run uvicorn squint.local.demo:app --port 9100

# 4. open http://localhost:9100 and press Run
```

The UI shows three panels side by side: the **original** (stays on your device), the **redacted** version, and **exactly what the server received**, read from the server's `/last` endpoint.

To run the agent without the UI:

```bash
uv run python -m squint.local.agent "Place my order"
```

### Redaction only, no model call

```bash
uv run python -m squint.local.pipeline shot.png http://localhost:8000/checkout.html   # with DOM hints
uv run python -m squint.local.pipeline shot.png                                        # pixels only
```

### Running on a real site (experimental)

```bash
uv run python -m squint.local.agent "Add the first phone to the cart and place the order using my details" https://www.demoblaze.com
```

Use a public practice store, not a real shop. Real sites have no `data-pii` tags, so Squint falls back to guessing field types from input attributes, and the agent fills forms from the fake values in `src/squint/local/profile.py`. Multi-step runs take a minute or two, since each step is a model call.

## Reproduce the benchmark

```bash
# put 5-10 face images (.jpg/.jpeg/.png) in bench/faces/ first, otherwise one fallback photo is used
uv run python bench/generate.py -n 200 --seed 0 --preview 6
uv run python bench/run_eval.py --tag full_s2 --face-tile 192
uv run python bench/run_eval.py --tag full_s1 --face-tile 192 --ocr-scale 1.0
uv run python bench/run_eval.py --tag full_s3 --face-tile 192 --ocr-scale 3.0
uv run python bench/report.py       # writes bench/results/table.md and recall_vs_latency.png
```

Ground truth is free: each template tags sensitive elements with `data-pii="..."`, and Playwright reads their bounding boxes after rendering. `bench/redact_previews.py` writes before/after images for the preview screenshots.

`bench/faces/` and `bench/data/` are gitignored. Face photos are not redistributed, so numbers will differ slightly with different photos.

## Project layout

```
src/squint/
  schemas.py            Box, RedactedBox, Target, ActionRequest, ActionResponse
  local/                runs on your device
    capture.py          screenshot, DOM hints, clickable-element targets
    detect/             ocr.py, patterns.py, merge.py, faces.py
    redact.py           solid-fill redaction + numbered labels
    pipeline.py         orchestration + per-stage timings
    executor.py         click/type + local placeholder resolution
    agent.py            the capture → redact → ask → act loop
    demo.py             local demo app serving ui/
    profile.py          fake values used to fill placeholders
  server/               only ever receives redacted images
    main.py             FastAPI: /act, /last, /health
    vlm.py              Groq vision call with a forced tool call
    prompts.py          prompt explaining the redaction scheme
mock_site/              demo checkout page
ui/                     three-panel demo page
bench/                  generator, eval harness, metrics, ablations, report
```

## Privacy notes

- Redaction is solid fill, not blur, so redacted pixels can't be reconstructed from what the server receives.
- The vision model provider (Groq) sees the redacted image and the region metadata above.

## Roadmap

- Browser extension that talks to the local service, so the agent can work in your own tabs.
- A small learned classifier for names and other pattern-free PII.
- A detector that handles small faces.

## Built with

Python, FastAPI, Playwright, Tesseract, MediaPipe, OpenCV, Groq, Pydantic, Faker, Jinja2, Matplotlib.
