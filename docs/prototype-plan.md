# Review prototype plan

Implementation scope: local Python CLI, fictional fixtures, reversible human decisions, and optional explicitly configured GPU adapters. Preserve historical proposal files and unrelated worktree state. NeuroAI assets, automatic model downloads and service startup are outside this implementation scope. Git publication is managed separately.

1. Implement and test a standard-library core: bounded JSON/media import, full timeline coverage cues, explicit fixed baseline policy, tool-call budget and trace, pending review output, accept/reject/revert and transcript/audit export.
2. Add a real Whisper CUDA adapter only for an explicitly supplied existing checkpoint and supported runtime. Reject unavailable CUDA, oversized context, unsupported media and runtime failures. No CPU fallback or automatic model download.
3. Keep model-based policy separate from the fixed baseline. Any model policy must choose from bounded actions and record its identity and decisions. Fixture evidence must remain visibly fictional and offline.

Input contract: `source.path` is relative to the JSON's media root, `source.duration` is finite positive seconds, and `segments` carry unique `id`, finite `start`/`end`, and original `text`. Optional speaker metadata is preserved. Missing timestamps require an upstream alignment adapter. Overlaps and gaps are review cues, not proof of transcript errors or omitted speech.

Output contract: review JSON preserves the full imported document and per-segment original text, candidate hypothesis, reason, source locator, pending/human status and tool/action trace. Pending export retains original text. Human decisions create a new review revision with an append-only decision history. No command overwrites existing output files.

Acceptance: reject invalid times, source traversal and oversized inputs; do not label unflagged/overlapping text correct or erroneous; hand failures/budget exhaustion to humans; preserve Chinese repetitions, negation and numbers through accept/revert/export. Use `unittest` without dependency installation for the core.
