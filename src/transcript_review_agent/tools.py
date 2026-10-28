"""Explicit tool implementations. Fixture results never represent model execution."""
from pathlib import Path

from .core import read_json


class ToolError(RuntimeError):
    pass


class FixtureTool:
    name = 'offline_fictional_fixture'

    def __init__(self, evidence: dict):
        self.evidence = evidence

    @classmethod
    def from_file(cls, path: Path | str):
        doc = read_json(path)
        if doc.get('provenance') != 'fictional_fixture_not_model_output':
            raise ToolError('fixture must explicitly declare fictional provenance')
        if not isinstance(doc.get('evidence'), dict):
            raise ToolError('fixture evidence must be an object')
        return cls(doc['evidence'])

    def retranscribe(self, source: Path, segment: dict, context: float, duration: float) -> dict:
        row = self.evidence.get(segment['id'])
        if row is None:
            raise ToolError('no fixture evidence for this segment')
        if not isinstance(row, dict):
            raise ToolError('invalid fixture evidence')
        if row.get('error'):
            raise ToolError(str(row['error']))
        return {'text': row.get('text'), 'resolved': row.get('resolved', True),
                'retryable': row.get('retryable',True),
                'reason': row.get('reason', 'offline fictional evidence for harness testing'),
                'provenance': 'fictional_fixture_not_model_output'}
