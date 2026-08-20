"""
Model setup helper for Auto Shorts.
With Ollama, model management is handled by the Ollama daemon.
Just run: ollama pull qwen3:4b
"""
import subprocess
import sys

MODEL = "qwen3:4b"

print(f"Pulling {MODEL} via Ollama...")
result = subprocess.run(["ollama", "pull", MODEL], check=False)
if result.returncode == 0:
    print(f"\nModel '{MODEL}' is ready.")
else:
    print(f"\nFailed to pull '{MODEL}'. Make sure Ollama is running: ollama serve")
    sys.exit(1)
