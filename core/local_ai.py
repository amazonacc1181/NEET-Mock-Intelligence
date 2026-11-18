from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import httpx
import psutil

from core import config

OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
Progress = Callable[[str], None]


def hardware_profile() -> dict[str, Any]:
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    free_disk_gb = round(shutil.disk_usage(config.ROOT).free / (1024 ** 3), 1)
    vram_gb = 0.0
    gpu_name = "Not detected"
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]
        if lines:
            gpu_name = lines[0].rsplit(",", 1)[0].strip()
            vram_gb = max(float(x.rsplit(",", 1)[1].strip()) / 1024 for x in lines)
    except Exception:
        pass
    return {
        "os": platform.platform(),
        "ram_gb": ram_gb,
        "free_disk_gb": free_disk_gb,
        "vram_gb": round(vram_gb, 1),
        "gpu": gpu_name,
        "python": sys.version.split()[0],
    }


def model_plan(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    p = profile or hardware_profile()
    ram = float(p["ram_gb"])
    vram = float(p.get("vram_gb", 0))
    disk = float(p["free_disk_gb"])
    usable_memory = max(ram, vram)
    if usable_memory >= 40 and disk >= 38:
        primary = "qwen3.8:27b"
        verifier = "deepseek-r1:14b"
        tier = "High accuracy"
        note = "The 27B multimodal model is selected for the main analyst; a separate reasoning model audits answers and matches."
        required_disk = 32
        embedding_model = "BAAI/bge-m3"
        enable_reranker = True
    elif usable_memory >= 20 and disk >= 19:
        primary = "qwen3.5:9b"
        verifier = "deepseek-r1:8b"
        tier = "Balanced"
        note = "A vision-capable 9B model handles analysis, with a smaller independent reasoning verifier."
        required_disk = 18
        embedding_model = "BAAI/bge-m3"
        enable_reranker = False
    elif usable_memory >= 12 and disk >= 9:
        primary = "qwen3.5:4b"
        verifier = ""
        tier = "Lightweight"
        note = "A smaller vision-capable model is selected. Accuracy and speed may be lower; independent AI verification is unavailable."
        required_disk = 8
        embedding_model = "BAAI/bge-small-en-v1.5"
        enable_reranker = False
    elif usable_memory >= 8 and disk >= 5:
        primary = "qwen3.5:2b"
        verifier = ""
        tier = "Minimum hardware"
        note = "This model can run on limited hardware, but is not recommended for a high-stakes full-bank analysis."
        required_disk = 4
        embedding_model = "BAAI/bge-small-en-v1.5"
        enable_reranker = False
    else:
        primary = ""
        verifier = ""
        tier = "Insufficient local resources"
        note = "Free disk/RAM is below the minimum recommended for local multimodal model inference."
        required_disk = 0
        embedding_model = "BAAI/bge-small-en-v1.5"
        enable_reranker = False
    if disk < required_disk:
        tier = "Insufficient disk space"
        note = f"The selected model plan needs about {required_disk} GB free disk space; only {disk} GB is available. Free disk space and retry."
    return {
        "tier": tier,
        "primary_model": primary,
        "verifier_model": verifier,
        "vision_model": primary,
        "embedding_model": embedding_model,
        "enable_reranker": enable_reranker,
        "note": note,
        "estimated_download_gb": required_disk,
    }


def ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Ollama" / "ollama.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                os.environ["PATH"] = str(candidate.parent) + os.pathsep + os.environ.get("PATH", "")
                return str(candidate)
    return None


def ollama_installed() -> bool:
    return ollama_executable() is not None


def ollama_running(timeout: float = 2.5) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            return client.get(f"{OLLAMA_URL}/api/tags").is_success
    except Exception:
        return False


def start_ollama(progress: Progress | None = None) -> None:
    progress = progress or (lambda _message: None)
    if ollama_running():
        return
    if not ollama_installed():
        raise RuntimeError("Ollama is not installed. Run setup_local_ai.bat again or install Ollama from https://ollama.com/download.")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen([ollama_executable(), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except Exception as exc:
        raise RuntimeError(f"Could not start Ollama: {exc}") from exc
    progress("Starting the local Ollama service…")
    for _ in range(40):
        if ollama_running():
            return
        time.sleep(1)
    raise RuntimeError("Ollama did not become ready. Open the Ollama desktop app and retry.")


def installed_models() -> set[str]:
    if not ollama_running():
        return set()
    try:
        with httpx.Client(timeout=10) as client:
            body = client.get(f"{OLLAMA_URL}/api/tags").json()
        return {str(x.get("name", "")) for x in body.get("models", [])}
    except Exception:
        return set()


def pull_model(model: str, progress: Progress | None = None) -> None:
    progress = progress or (lambda _message: None)
    progress(f"Downloading {model} from the public Ollama model registry…")
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream("POST", f"{OLLAMA_URL}/api/pull", json={"name": model, "stream": True}) as response:
                response.raise_for_status()
                last_line = ""
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status = payload.get("status", "Downloading model…")
                    total, completed = payload.get("total"), payload.get("completed")
                    if total:
                        pct = int(100 * completed / max(total, 1))
                        message = f"{model}: {status} — {pct}%"
                    else:
                        message = f"{model}: {status}"
                    if message != last_line:
                        progress(message)
                        last_line = message
                    if payload.get("error"):
                        raise RuntimeError(payload["error"])
    except Exception as exc:
        raise RuntimeError(f"Could not download {model}: {exc}") from exc


def write_local_environment(plan: dict[str, Any]) -> Path:
    if not plan.get("primary_model"):
        raise RuntimeError(plan.get("note", "No viable local model plan."))
    env_path = config.ROOT / ".env"
    values = {
        "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
        "LLM_API_KEY": "ollama",
        "LLM_MODEL": plan["primary_model"],
        "VERIFY_BASE_URL": "http://127.0.0.1:11434/v1" if plan.get("verifier_model") else "",
        "VERIFY_API_KEY": "ollama",
        "VERIFY_MODEL": plan.get("verifier_model", ""),
        "VISION_BASE_URL": "http://127.0.0.1:11434/v1",
        "VISION_API_KEY": "ollama",
        "VISION_MODEL": plan["vision_model"],
        "EMBEDDING_MODEL": plan.get("embedding_model", "BAAI/bge-m3"),
        "ENABLE_EMBEDDINGS": "true",
        "ENABLE_RERANKER": str(bool(plan.get("enable_reranker", False))).lower(),
        "RERANKER_MODEL": "BAAI/bge-reranker-v2-m3",
        "LLM_TEMPERATURE": "0.1",
        "LLM_TIMEOUT": "600",
        "LLM_MAX_RETRIES": "4",
        "LLM_BATCH_SIZE": "2" if "27b" in plan["primary_model"] else "3",
        "TOP_CANDIDATES": "60",
        "MAX_MATCHES_PER_NEET_QUESTION": "15",
        "OCR_ENABLED": "true",
        "RENDER_PAGE_IMAGES": "true",
        "VISION_MAX_IMAGES": "3",
    }
    lines = ["# Generated by NEET Mock Intelligence local AI setup. No cloud API key is used."]
    lines.extend(f"{key}={value}" for key, value in values.items())
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Apply the selected local model settings to the running Streamlit process too.
    config.LLM_BASE_URL = values["LLM_BASE_URL"]
    config.LLM_API_KEY = values["LLM_API_KEY"]
    config.LLM_MODEL = values["LLM_MODEL"]
    config.VERIFY_BASE_URL = values["VERIFY_BASE_URL"]
    config.VERIFY_API_KEY = values["VERIFY_API_KEY"]
    config.VERIFY_MODEL = values["VERIFY_MODEL"]
    config.VISION_BASE_URL = values["VISION_BASE_URL"]
    config.VISION_API_KEY = values["VISION_API_KEY"]
    config.VISION_MODEL = values["VISION_MODEL"]
    config.EMBEDDING_MODEL = values["EMBEDDING_MODEL"]
    config.ENABLE_EMBEDDINGS = True
    config.ENABLE_RERANKER = bool(plan.get("enable_reranker", False))
    config.RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
    config.LLM_BATCH_SIZE = int(values["LLM_BATCH_SIZE"])
    config.LLM_TIMEOUT = int(values["LLM_TIMEOUT"])
    config.TOP_CANDIDATES = int(values["TOP_CANDIDATES"])
    config.MAX_MATCHES_PER_NEET_QUESTION = int(values["MAX_MATCHES_PER_NEET_QUESTION"])
    config.VISION_MAX_IMAGES = int(values["VISION_MAX_IMAGES"])
    return env_path


def configure_local_ai(progress: Progress | None = None) -> dict[str, Any]:
    progress = progress or (lambda _message: None)
    profile = hardware_profile()
    plan = model_plan(profile)
    if not plan.get("primary_model") or plan["tier"].startswith("Insufficient"):
        raise RuntimeError(plan["note"])
    if not ollama_installed():
        raise RuntimeError("Ollama is not installed. Use setup_local_ai.bat (Windows) or install it from https://ollama.com/download, then click Configure local AI again.")
    start_ollama(progress)
    models = installed_models()
    for model in [plan["primary_model"], plan.get("verifier_model", "")]:
        if model and model not in models:
            pull_model(model, progress)
    env_path = write_local_environment(plan)
    return {"hardware": profile, "plan": plan, "env_path": str(env_path), "installed_models": sorted(installed_models())}


def connection_status() -> dict[str, Any]:
    running = ollama_running()
    models = installed_models() if running else set()
    return {"installed": ollama_installed(), "running": running, "models": sorted(models), "url": OLLAMA_URL}