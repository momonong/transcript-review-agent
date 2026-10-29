"""Start the local review workbench without installing the package or GPU extras."""
from pathlib import Path
import sys

if sys.version_info < (3,11):
    raise SystemExit('Transcript Review Agent requires Python 3.11 or newer.')

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from transcript_review_agent.__main__ import main

if __name__=='__main__':
    raise SystemExit(main(['serve',*sys.argv[1:]]))
