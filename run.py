#!/usr/bin/env python3
import subprocess
import webbrowser
import time
import sys
import os
# import signal

def main():
    print("Starting AI Agent Desktop App...")
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    venv_python = os.path.join(project_dir, ".venv", "bin", "python")
    venv_uvicorn = os.path.join(project_dir, ".venv", "bin", "uvicorn")
    
    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found. Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)
    
    print("Starting server...")
    server_process = subprocess.Popen(
        [venv_uvicorn, "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    time.sleep(2)
    
    print("Opening browser...")
    webbrowser.open("http://localhost:8000")
    
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
