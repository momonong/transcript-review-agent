# Prototype validation

2026-10-28. These observations describe a local prototype, not a result for the earlier concept proposal.

## Standard-library core

- A fictional fixture run completed import, fixed-baseline review, scripted accept, scripted revert, and transcript/audit export. These actions exercise the human-decision interface without claiming an independent reviewer accepted quality. Fixture evidence explicitly says `fictional_fixture_not_model_output`; its generated audio is silent synthetic WAV, so it is not an ASR-accuracy demonstration.
- Twenty standard-library tests pass. They cover invalid time bounds, gap/overlap cues, tool failures and budget exhaustion, original retention, accept/reject/revert, Chinese repetition/negation/numbers, source traversal, input-size limits, bounded context expansion, output overwrite refusal, original schema/hash consistency, decision-history consistency, malformed decision identities, and cross-directory source location.
- CUDA adapter boundary tests cover exact PCM16 WAV extraction, declared-duration mismatch, oversized clips, explicit local checkpoint requirements, rejection of CPU requests, and missing-EOS truncation. The adapter explicitly requests raw `output.sequences` with `return_dict_in_generate=True`, because Whisper's tensor-only return strips EOS. Target and context hypotheses carry separate termination metadata. Missing EOS is unresolved and hands off without repeating a nonretryable decode. These boundary tests do not execute a model, and EOS only verifies decoding termination, not transcript correctness.
- The current action policy is `fixed_baseline`. It is not an LLM agent. A model-based action policy has not been implemented or validated.

Run from the repository root with the core package on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "$PWD/src"
python -B -m unittest discover -s tests -v
```

## Independent host GPU probe

An independent local probe completed real inference around **2026-10-28 17:04 Asia/Taipei**, with the existing public `openai/whisper-medium` snapshot at revision `abdf7c39ab9d0397620ccaea8974cc764cd0953e`.

| Observation | Single-probe result |
|---|---|
| Input | 9.722-second Windows SAPI synthetic fictional English speech |
| Device | NVIDIA GeForce RTX 5090 Laptop GPU |
| Runtime | PyTorch 2.7.1+cu128, CUDA 12.8 |
| Model load | 1.491 seconds |
| Inference | 1.089 seconds |
| Peak allocated GPU memory | 1690.3 MiB |
| Language/task handling | Explicit tokenizer-derived legacy decoder prompt |
| Output | `I, I did not take 15. I took 50. No, 51. We do not need more tomorrow.` |

The older local snapshot lacked generation language metadata. The successful probe selected the English transcription decoder prompt explicitly in memory, without editing the cache. The CLI adapter records modern versus legacy handling in each evidence record.

This is one host GPU inference probe, not a benchmark or quality evaluation. It does not establish Mandarin accuracy, an agent contribution, lower human effort, shorter end-to-end completion, USB compatibility, power savings, or institutional approval. The Whisper medium host probe does not validate Whisper Small on UGen300 USB. Raw audio, detailed probe logs, model locations, and private runtime paths stay in ignored local files. No USB test has run.

## CLI CUDA integration

Around **2026-10-28 17:09 Asia/Taipei**, a real CLI run imported the staged source and manually seeded initial draft, called the CUDA Whisper tool once, and wrote a pending review with actual model hypotheses while preserving the original. The candidate retained the synthetic repetition, negation and numbers. This verifies integration, not independent human quality acceptance.

Around **17:14**, the hardened review schema completed a fresh CUDA review followed by scripted accept, revert and export. The export restored the seeded original text, and the audit retained the actual CUDA hypothesis. Explicit local locators, original integrity checks and human-decision replay checks participated in that run.

An initial EOS guard incorrectly handed off a normal decode because Whisper's default tensor-only return strips EOS during postprocessing. The adapter now explicitly requests `return_dict_in_generate=True` and checks the genuine raw `output.sequences`, without guessing completion from length or weakening the guard. Around **17:20**, a fresh real CLI CUDA run confirmed `target_termination.complete=true` and `ended_with_eos=true`, retained the original text, and offered the model hypothesis with **pending** status. All **20 tests** pass. Missing-EOS/truncated-output handling remains a boundary test rather than a claim about model accuracy.

These engineering results occurred after the originally stated **17:00 deadline**. Historical proposal files keep their design-stage status. The prototype evidence does not retroactively establish that implementation existed before the deadline and does not imply that a competition accepts later supplements.

No automatic model download or training is part of this prototype. Original hashes and decision replay checks detect inconsistent/corrupted records; they are not digital signatures or protection against a person deliberately forging an entire document.
