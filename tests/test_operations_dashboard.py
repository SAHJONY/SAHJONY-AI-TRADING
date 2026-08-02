import re
import subprocess
from pathlib import Path


def test_operations_dashboard_script_parses_as_javascript(tmp_path):
    html = Path("public/operations.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    assert scripts
    script = tmp_path / "operations.js"
    script.write_text("\n".join(scripts), encoding="utf-8")
    subprocess.run(["node", "--check", str(script)], check=True, capture_output=True, text=True)
