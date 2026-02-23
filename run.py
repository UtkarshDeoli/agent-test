#!/usr/bin/env python3
import subprocess
import webbrowser
import time
import sys
import os
import urllib.request
import urllib.error


def is_server_healthy(health_url: str) -> bool:
    try:
        with urllib.request.urlopen(health_url, timeout=1) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def wait_for_server(server_process, health_url: str, timeout_seconds: int = 15) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if server_process.poll() is not None:
            return False

        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            pass

        time.sleep(0.5)

    return False

def main():
    print("Starting AI Agent Desktop App...")
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    venv_python = os.path.join(project_dir, ".venv", "bin", "python")
    
    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found. Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)

    health_url = "http://127.0.0.1:8000/health"
    app_url = "http://localhost:8000"

    if is_server_healthy(health_url):
        print("Server is already running on http://127.0.0.1:8000")
        print("Opening browser...")
        webbrowser.open(app_url)
        return
    
    print("Starting server...")
    server_process = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
    )

    if not wait_for_server(server_process, health_url):
        if is_server_healthy(health_url):
            print("An existing AI Agent instance is already running on port 8000.")
            print("Opening browser...")
            webbrowser.open(app_url)
            return

        if server_process.poll() is None:
            print("Error: Server did not become healthy within 15 seconds.")
            server_process.terminate()
            server_process.wait()
        else:
            print(f"Error: Server exited during startup (code: {server_process.returncode}).")

        print("Run this for full logs:")
        print(f"{venv_python} -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        sys.exit(1)
    
    print("Opening browser...")
    webbrowser.open(app_url)
    
    print("\n" + "=" * 50)
    print("AI Agent is running!")
    print("Press Ctrl+C to stop the server")
    print("=" * 50 + "\n")
    
    try:
        server_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server_process.terminate()
        server_process.wait()
        print("Goodbye!")

if __name__ == "__main__":
    main()
