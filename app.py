from __future__ import annotations

import runpy
import sys
from pathlib import Path

# Permite execução transparente do dashboard modular via `streamlit run app.py`
# mantendo compatibilidade com a raiz do repositório
DASHBOARD_SCRIPT = Path(__file__).resolve().parent / "dashboard" / "app.py"

if __name__ == "__main__" or "streamlit" in sys.modules:
    runpy.run_path(str(DASHBOARD_SCRIPT), run_name="__main__")