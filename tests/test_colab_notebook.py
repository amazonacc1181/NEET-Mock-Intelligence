import ast
import base64
import io
import json
import zipfile
from pathlib import Path


def test_colab_notebook_is_self_contained_and_valid_python():
    notebook_path = Path(__file__).resolve().parents[1] / "NEET_Mock_Intelligence_Colab.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code_cells = [cell["source"] for cell in notebook["cells"] if cell.get("cell_type") == "code"]
    for source in code_cells:
        ast.parse("".join(source) if isinstance(source, list) else source)

    all_source = "\n".join("".join(source) if isinstance(source, list) else source for source in code_cells)
    marker = 'PROJECT_BUNDLE_B64 = """'
    assert marker in all_source
    encoded = all_source.split(marker, 1)[1].split('"""', 1)[0]
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded)))
    names = set(archive.namelist())
    assert {"app.py", "core/workflow.py", "core/config.py", "core/database.py", "core/reporting.py", "requirements-colab.txt"} <= names


def test_colab_full_analysis_requires_gpu_and_uses_two_local_models():
    notebook_path = Path(__file__).resolve().parents[1] / "NEET_Mock_Intelligence_Colab.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    all_source = "\n".join("".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"] for cell in notebook["cells"] if cell.get("cell_type") == "code")
    assert "torch.cuda.is_available()" in all_source
    assert "qwen3.5:9b" in all_source
    assert "deepseek-r1:8b" in all_source
    assert "No GPU is attached" in all_source