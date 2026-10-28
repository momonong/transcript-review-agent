# transcript-review-agent

## Local prototype

The repository now includes a runnable Python **fixed-policy baseline harness**, not a completed LLM agent. It imports bounded, time-aligned ASR drafts, checks the complete declared timeline for gap/overlap cues, records bounded tool actions, preserves original text, and supports reversible human decisions and transcript/audit export. Gaps are not proof of missing speech, overlaps may be legitimate, and unflagged text is never labelled correct. Prototype work does not establish the proposal's quality or efficiency benefits.

The core requires Python 3.11+ and no third-party packages. From the repository root, in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD/src"
python -B examples/make_fictional_fixture.py --out .local/fictional
python -B -m transcript_review_agent review .local/fictional/input.json --fixture .local/fictional/evidence.json --out .local/review.json --budget 3
python -B -m transcript_review_agent decide .local/review.json s1 accept --reviewer demo --out .local/accepted.json
python -B -m transcript_review_agent decide .local/accepted.json s1 revert --reviewer demo --out .local/reverted.json
python -B -m transcript_review_agent export .local/reverted.json --out-dir .local/export
python -B -m unittest discover -s tests -v
```

The fixture creates silent synthetic WAV audio and explicitly fictional evidence. It tests the review/audit workflow, **not speech recognition accuracy or a successful model run**. Outputs are exclusive-create and will refuse existing files. Use a new output path for another run. Pending, rejected and reverted items retain original text on export. The full original, candidates, evidence, tool trace and human decisions remain in `audit.json`.

Input JSON requires `source.path` (relative to the input's directory or `--media-root`), `source.duration` in seconds, and unique segments with `id`, `start`, `end`, `text`. Keep any speaker metadata. Source traversal and symlinks escaping the media root are rejected. Defaults: JSON at most 2 MiB, source at most 512 MiB, duration at most 24 hours. The current coverage duration comes from declared input metadata, not an audio-content correctness check. Missing timestamps require an upstream alignment/import adapter.

An optional Transformers Whisper CUDA adapter accepts an **existing local checkpoint directory**. It uses `local_files_only=True`, float16 and explicit language/task, requires CUDA, and never downloads or falls back to CPU. Example in a separately verified torch/transformers runtime:

```powershell
python -B -m transcript_review_agent review path/to/input.json --whisper-model path/to/local/whisper-checkpoint --language zh --device cuda:0 --out .local/gpu-review.json --budget 2 --context 1.5
```

This adapter currently accepts mono 16 kHz PCM16 WAV only and checks the declared duration against actual WAV frames. Other media need explicit conversion. Each selected tool action decodes the exact target and, when requested, its wider context (at most two model generations). Only the exact-target hypothesis becomes a pending candidate. The context hypothesis remains separate evidence. Clips above 30 seconds fail explicitly. A legacy Whisper snapshot lacking language generation metadata uses explicit tokenizer-derived forced decoder IDs in memory, with the branch recorded in evidence. No cache files are changed.

Target and context decodes must terminate with EOS before a pending candidate is offered. Missing EOS, including a possible token-limit truncation, becomes unresolved evidence and requires human review. EOS confirms decoding termination, not transcription accuracy.

Model-based action policy is not yet implemented: every current run is labelled `fixed_baseline`, not an LLM agent. A fixture run does not imply model inference, USB execution, deployment or efficiency benefits. See [prototype plan](docs/prototype-plan.md).

Use a Python interpreter from a separately verified CUDA environment for the optional adapter, and pass the model directory explicitly. Runtime packages and checkpoint weights are not bundled or automatically installed. The core has a dependency-free `uv.lock`; that lock does not reproduce the optional GPU environment. Supported-model listings and a host checkpoint are not proof of USB compatibility.

Review/audit files contain an explicit absolute local source locator so saving a review in another directory does not silently reinterpret the original relative source path. Keep these files under ignored `.local/` or another private location. Original-document hashes, schema checks and decision replay reject inconsistent files; they do not provide cryptographic signatures. Early development review files missing these fields must be regenerated rather than silently repaired.

Project documents: [concept](docs/concept.md), [prototype plan](docs/prototype-plan.md), and [validation](docs/validation.md).

## Proposal materials

Local historical proposal drafts remain preserved in the existing proposal directory and are not included in the prototype source publication. They describe the design-stage status at preparation time. Current prototype status is documented above and in the project documents. NeuroAI experience and historical processing-time estimates are supporting background, not evidence of this agent's effectiveness. No NeuroAI code, patient data or private recordings are included in the prototype.
