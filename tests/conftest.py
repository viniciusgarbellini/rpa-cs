import sys
from pathlib import Path

# Permite importar src.* a partir dos testes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
