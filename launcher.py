"""
launcher.py — Lance l'API FastAPI + l'interface PyQt6 en séquence.
Usage : .\\environment\\python.exe launcher.py
"""
from __future__ import annotations
import sys
import os
import time
import subprocess
import threading
import socket
import urllib.request
import json as _json
from pathlib import Path

API_HOST = "127.0.0.1"
API_PORT = 8502
PYTHON   = str(Path(__file__).parent / "environment" / "python.exe")

def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    """Attend que le port soit ouvert (API prête)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def kill_port(port: int):
    """Tue tout processus qui occupe déjà le port via PowerShell (indépendant de la langue)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess"],
            capture_output=True, text=True, timeout=10
        )
        my_pid = str(os.getpid())
        killed = False
        for pid in set(p.strip() for p in result.stdout.splitlines() if p.strip().isdigit()):
            if pid != my_pid:
                print(f"[INFO] Port {port} occupé par PID {pid} → arrêt forcé…", flush=True)
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                killed = True
        if killed:
            print(f"[INFO] Attente libération port {port}…", flush=True)
            time.sleep(2)  # Laisser l'OS libérer le port
    except Exception as e:
        print(f"[WARN] Impossible de libérer le port {port} : {e}", flush=True)


def start_api():
    """Libère le port si occupé, puis démarre uvicorn (logs visibles dans ce terminal)."""
    kill_port(API_PORT)
    time.sleep(0.3)
    cmd = [PYTHON, "-m", "uvicorn", "api.main:app",
           "--host", API_HOST, "--port", str(API_PORT),
           "--no-access-log", "--log-level", "warning"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent)
    proc = subprocess.Popen(
        cmd, cwd=str(Path(__file__).parent), env=env,
    )
    return proc


def main():
    print("=== PressiomètreIA v2 ===")
    print("Démarrage de l'API FastAPI…")

    api_proc = start_api()

    print(f"Attente du port {API_PORT}…", end="", flush=True)
    if not wait_for_port(API_HOST, API_PORT, timeout=60):
        print("\n❌ L'API n'a pas démarré dans les 60 secondes.")
        api_proc.kill()
        sys.exit(1)
    print(" OK ✅")

    # ── Chargement KIBALI NF4 4-bit ──────────────────────────────────────────
    print("─" * 60)
    print(" Chargement KIBALI — Mistral-7B NF4 4-bit")
    print(" (les logs [KIBALI] s'affichent ci-dessous en temps réel)")
    print("─" * 60)
    spinner = ["|", "/", "─", "\\"]
    t_kibali = time.time()
    si = 0
    kibali_ok = False
    MIN_WAIT = 5.0   # Ne pas déclarer prêt avant 5s (évite l'ancienne instance)
    TIMEOUT  = 300.0 # 5 min max pour charger le modèle
    while True:
        elapsed = time.time() - t_kibali
        if elapsed > TIMEOUT:
            print(f"\r ❌ KIBALI timeout ({TIMEOUT:.0f}s) — modèle non chargé.          ")
            break
        try:
            url = f"http://{API_HOST}:{API_PORT}/kibali/status"
            with urllib.request.urlopen(url, timeout=2) as r:
                data = _json.loads(r.read())
            if data.get("ready") and elapsed >= MIN_WAIT:
                print(f"\r KIBALI prêt ✅  — modèle chargé en {elapsed:.0f}s            ")
                kibali_ok = True
                break
            if data.get("error"):
                print(f"\r KIBALI ERREUR ❌ : {data['error']}                            ")
                break
        except Exception:
            pass
        print(f"\r {spinner[si % 4]} Attente chargement NF4… {elapsed:.0f}s", end="", flush=True)
        si += 1
        time.sleep(1.0)
    print("─" * 60)
    if not kibali_ok:
        print(" ⚠  KIBALI indisponible — l'IA ne fonctionnera pas.")
        print("─" * 60)

    # S'assurer que la racine du projet est dans sys.path
    root = str(Path(__file__).parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("PYTHONPATH", root)
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from frontend.main_window import MainWindow
    from frontend.icon_factory import get_app_icon, ensure_ico_file

    app = QApplication(sys.argv)
    app.setApplicationName("PressiomètreIA v2")
    app.setOrganizationName("SETRAF GABON")

    # ── Icône de l'application (barre des tâches, titre fenêtre, Alt+Tab) ─
    _icon = get_app_icon()
    app.setWindowIcon(_icon)

    # ── Fichier .ico pour l'intégration shell Windows ──────────────────────
    _assets = Path(__file__).parent / "assets"
    ensure_ico_file(
        str(_assets / "pressiometre.ico"),
        str(_assets / "pressiometre_logo.png"),
    )

    win = MainWindow()
    win.show()

    exit_code = app.exec()

    print("Fermeture de l'API…")
    api_proc.terminate()
    try:
        api_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        api_proc.kill()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
