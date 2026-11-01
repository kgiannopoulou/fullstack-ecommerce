import sys
from pathlib import Path

# The pipeline modules live in src/ and import each other by name.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
