from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.local_ai import configure_local_ai, hardware_profile, model_plan


def install_ollama_if_possible() -> None:
    from core.local_ai import ollama_installed
    if ollama_installed():
        return
    system = platform.system()
    if system == "Windows" and shutil.which("winget"):
        print("Installing Ollama with Windows Package Manager…")
        result = subprocess.run([
            "winget", "install", "--id", "Ollama.Ollama", "-e",
            "--accept-package-agreements", "--accept-source-agreements",
        ], check=False)
        if result.returncode == 0 and ollama_installed():
            return
    elif system == "Darwin" and shutil.which("brew"):
        print("Installing Ollama with Homebrew…")
        result = subprocess.run(["brew", "install", "--cask", "ollama"], check=False)
        if result.returncode == 0 and ollama_installed():
            return
    elif system == "Linux":
        print("Installing Ollama using its official installer…")
        subprocess.run(["bash", "-lc", "curl -fsSL https://ollama.com/install.sh | sh"], check=False)
        if ollama_installed():
            return
    print("\nOllama could not be installed automatically.")
    print("Install it from https://ollama.com/download, reopen this folder, and run this setup again.")
    raise SystemExit(2)


def main() -> int:
    print("NEET Mock Intelligence — local AI setup (no API keys, no paid API)")
    print("Models are downloaded from Ollama's public registry and run on this computer.\n")
    profile = hardware_profile()
    plan = model_plan(profile)
    print(f"System RAM: {profile['ram_gb']} GB | GPU: {profile['gpu']} | VRAM: {profile['vram_gb']} GB | free disk: {profile['free_disk_gb']} GB")
    print(f"Recommended tier: {plan['tier']}")
    print(f"Main model: {plan['primary_model'] or 'None'}")
    print(f"Independent verifier: {plan['verifier_model'] or 'Not available on detected hardware'}")
    print(plan['note'])
    if not plan.get("primary_model") or plan["tier"].startswith("Insufficient"):
        return 2
    install_ollama_if_possible()
    try:
        def progress(message: str) -> None:
            print(message, flush=True)
        result = configure_local_ai(progress)
        print("\nLocal AI is ready.")
        print(f"Configuration saved to: {result['env_path']}")
        print("Start the app with run_windows.bat / run_mac_linux.sh.")
        return 0
    except Exception as exc:
        print(f"\nSetup error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())