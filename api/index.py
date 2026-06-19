import json
import subprocess
import sys
from pathlib import Path

def handler(event, context=None):
    """Vercel serverless function entry point.
    Executes the trading bot in dry‑run mode and returns its stdout/stderr.
    Vercel's Python runtime invokes the function with ``event`` (the request
    payload) and an optional ``context`` argument, mirroring AWS Lambda.
    """
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--dry-run"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"stdout": result.stdout, "stderr": result.stderr}),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
