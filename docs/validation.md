# Prototype validation

Engineering checkpoints on 2026-10-28 and 2026-10-29. These observations describe a local prototype, not a result for the earlier concept proposal.

## Standard-library core

- A fictional fixture run completed import, fixed-baseline review, scripted accept, scripted revert, and transcript/audit export. These actions exercise the human-decision interface without claiming an independent reviewer accepted quality. Fixture evidence explicitly says `fictional_fixture_not_model_output`; its generated audio is silent synthetic WAV, so it is not an ASR-accuracy demonstration.
- At the first CLI checkpoint, twenty standard-library tests passed. They covered invalid time bounds, gap/overlap cues, tool failures and budget exhaustion, original retention, accept/reject/revert, Chinese repetition/negation/numbers, source traversal, input-size limits, bounded context expansion, output overwrite refusal, original schema/hash consistency, decision-history consistency, malformed decision identities, and cross-directory source location. Later workbench and policy tests extend that suite.
- CUDA adapter boundary tests cover exact PCM16 WAV extraction, declared-duration mismatch, oversized clips, explicit local checkpoint requirements, rejection of CPU requests, and missing-EOS truncation. The adapter explicitly requests raw `output.sequences` with `return_dict_in_generate=True`, because Whisper's tensor-only return strips EOS. Target and context hypotheses carry separate termination metadata. Missing EOS is unresolved and hands off without repeating a nonretryable decode. These boundary tests do not execute a model, and EOS only verifies decoding termination, not transcript correctness.
- The first checkpoint used `fixed_baseline`. A bounded LLM policy and its actual synthetic run were added later, as recorded below; the original baseline evidence does not become agent evidence retroactively.

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

## Chinese workbench and bounded LLM run, 2026-10-29

The local workbench can display source audio, imported text, a target candidate and word differences; accept, retain or revert changes; and download the transcript and audit. The portable demo contains only legal author-written synthetic speech and recorded model results. Opening it does not load a model or re-run inference. Its default selection is the omitted-utterance example, s3.

One actual host GPU run combined Microsoft Phi-4-mini-instruct, pinned revision `cfbefacb99257ffa30c83adab238a50856ac3083`, with the existing OpenAI Whisper medium checkpoint:

| Recorded observation | Result |
|---|---|
| Source | Four Chinese synthetic segments, 27.3775 seconds, Windows SAPI |
| Initial draft | Includes manually seeded errors and a control segment |
| LLM decisions | 8 |
| Whisper tool calls | 4, each with target and context decoding |
| Selected context seconds | 6 / 3 / 3 / 6 |
| Pending candidates | s3 and s4 |
| Explicit human handoffs | s1 and s2 |
| Handoff cause | Phi returned Markdown-fenced JSON, which the strict parser rejected |
| Review-loop duration | 12.3569 seconds, excluding checkpoint hashing, model loading and human work |
| Device | NVIDIA GeForce RTX 5090 Laptop GPU |

The failed actions remain in the [actual agent trace](results/chinese-agent-result.json). They were not normalized, hidden or converted into successful decisions. A [fixed-process record](results/chinese-baseline-result.json) from the same synthetic source is available for inspection, but this is not the proposed matched A/B/C benefit study. Two candidates and two handoffs are routing outcomes, not accuracy or labor-saving rates. Reading scripts are synthetic source material, not independent human ground truth, and were not supplied to the policy.

All 47 Python tests pass, including workbench Host/Origin/token boundaries, source-content verification, bounded byte-range playback, exclusive revision storage, stale-version rejection, failed-job preservation, policy action constraints and incomplete generation. A separate browser-independent JavaScript regression passes after reproducing a temporary polling failure; it confirms recovery without duplicate timers or losing the last visible result. Neither these tests nor the recorded model run establish human final-quality acceptance or reduced review effort.

## Browser-operated live GPU workbench check, 2026-10-29

A real browser started the configured local GPU job through the workbench and received a completed `llm_agent` review for all four synthetic segments. An automated browser action then accepted the s3 candidate and downloaded the transcript JSON. Reading the actual downloaded file confirmed that s3 had `review_status=accepted` and exactly matched its recorded model candidate. The other three exported segments retained their imported text. This checks the live job, decision and download path, not independent human quality acceptance.

At approximately **11:05 Asia/Taipei**, the same browser workflow reverted s3 successfully. The saved review contained two decision records, and exporting it through the core restored the exact imported text, `先確認時間。最後再寄出通知。`, with `review_status=reverted`. This is a verified browser-operated accept/revert path, separate from the earlier scripted CLI checks and from independent human quality acceptance.

The final interface was checked in actual browser windows at desktop **1440 px**, tablet **768 px** and phone **390 px**. The tablet and phone document scroll widths were **753 px** and **375 px**, respectively, within their viewports; the phone app used its stacked flex layout. The [desktop screenshot](images/workbench.jpg) is embedded in the README. Tablet and phone screenshots remain local QA artifacts. These checks verify layout and interaction at the tested sizes, not universal browser or device compatibility.
