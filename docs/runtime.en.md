# Local runtime

English | [繁體中文](runtime.zh-Hant.md)

## Demo without a GPU

From the repository root, with Python 3.11 or newer:

```powershell
python app.py
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/) on the same computer. This path uses only the Python standard library. It reads the bundled four-segment Chinese synthetic audio and a recorded GPU review; it does not import torch, download models or run inference.

The interface defaults to English. The **Language** selector also offers Traditional Chinese and remembers an explicit choice if browser storage is available. Language changes do not translate the source, candidate or raw evidence, and do not reset the selected segment, reviewer input or playback.

To open an existing review:

```powershell
python app.py --review your-review.json
```

The server binds only to `127.0.0.1`. Use `--port 8767` if the default port is occupied. Each human decision saves a new revision in `.local/workbench/revisions`, or a location supplied with `--save-dir`; it never overwrites the original review or audio. The browser does not automatically reopen a previously saved revision on restart: pass its review file explicitly.

The full audit includes local source locators. Keep private audits local and inspect them before sharing. Content changes, integrity failures and revision conflicts are rejected rather than silently repaired.

## Optional GPU environment

The `gpu` extra in `pyproject.toml` and `uv.lock` declare pinned packages. torch comes explicitly from the official CUDA 12.8 index; the other packages come from PyPI. To create this project's own `.venv`:

```powershell
uv sync --locked --extra gpu --python 3.11
```

This installs packages, not model weights. The earlier environment checkpoint resolved lock metadata without running this installation or changing the shared, verified GPU environment. A clean environment and other devices still require actual execution checks.

The recorded host environment used these versions; they are not a compatibility guarantee for another device:

| Component | Recorded version |
|---|---|
| Python | 3.11.15 |
| torch | 2.7.1+cu128 |
| transformers | 4.57.6 |
| tokenizers | 0.22.2 |
| numpy | 2.3.5 |
| huggingface-hub | 0.36.0 |
| safetensors | 0.7.0 |

Adapters require CUDA and do not silently fall back to the CPU. Whisper uses float16; the Phi action policy uses bfloat16 and native SDPA. Memory, runtime and output quality require device testing; installing the packages does not verify the workflow.

## Model provenance and local weights

- Speech tool: [OpenAI Whisper medium](https://huggingface.co/openai/whisper-medium), verified snapshot revision `abdf7c39ab9d0397620ccaea8974cc764cd0953e`.
- Action policy: [Microsoft Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct), pinned adapter revision `cfbefacb99257ffa30c83adab238a50856ac3083`; both official weight shards are checked by SHA256.
- Both adapters read explicitly supplied local weights with `local_files_only=True`. They do not use remote custom model code or automatically download or replace models.
- Phi selects bounded actions and observed tool evidence. It cannot generate a new transcript for direct acceptance or accept a change for a person.

Set `WHISPER_MODEL` and `PHI_MODEL` to your actual local checkpoint directories, then use the GPU environment's Python:

```powershell
uv run --locked --extra gpu python app.py --input your-input.json --whisper-model "$env:WHISPER_MODEL" --agent-model "$env:PHI_MODEL" --policy agent
```

Opening the page does not load models. Press **Run review** to start a bounded background job. Without configured models, the demo hides that control. Runtime, weights, tool or policy failures are shown while the previous result is retained. A session with human decisions cannot be rerun over that history; open a new input session instead.

The speech tool currently requires **mono, 16 kHz, PCM16 WAV**, with a maximum 30-second interval per call. Other formats, missing timestamps and longer intervals require an explicit adapter workflow. Whisper medium on the host GPU does not establish compatibility for Whisper Small on UGen300 USB; USB execution has not been tested.

## Input contract and CLI fixture

Input JSON contains a relative `source.path`, a finite positive `source.duration` in seconds, and segments with unique `id`, finite `start` / `end` and original `text`. Optional speaker and other metadata are preserved. Missing timestamps require upstream alignment. Timeline gaps and overlaps are review cues, not proof of omitted or incorrect speech.

The standard-library core can be exercised using a clearly fictional fixture:

```powershell
$env:PYTHONPATH = "$PWD/src"
python -B examples/make_fictional_fixture.py --out .local/fictional
python -B -m transcript_review_agent review .local/fictional/input.json --fixture .local/fictional/evidence.json --out .local/review.json
python -B -m transcript_review_agent decide .local/review.json s1 accept --reviewer demo --out .local/accepted.json
python -B -m transcript_review_agent decide .local/accepted.json s1 revert --reviewer demo --out .local/reverted.json
python -B -m transcript_review_agent export .local/reverted.json --out-dir .local/export
```

This fixture uses silent audio and evidence labeled `fictional_fixture_not_model_output`. It tests decisions and audit preservation, not speech recognition. Outputs refuse to overwrite existing files; choose new output locations when repeating the commands.

## Development verification

```powershell
$env:PYTHONPATH = "$PWD/src"
python -B -m unittest discover -s tests -v
node tests/test_workbench_js.mjs
```

See [recorded validation](validation.md) for actual model runs, tested boundaries and limitations. Engineering validation, model inference, browser operation and independent human quality acceptance are separate claims.
