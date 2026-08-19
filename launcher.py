import subprocess
import os
import sys
import webbrowser
import time

def start_backend():
    # Activate venv and run uvicorn
    backend_dir = os.path.join(os.getcwd(), 'backend')
    venv_python = os.path.join(backend_dir, 'venv', 'Scripts', 'python.exe')
    
    if not os.path.exists(venv_python):
        print("Backend virtual environment not found.")
        sys.exit(1)
        
    cmd = [venv_python, "-m", "uvicorn", "main:app", "--port", "8000"]
    return subprocess.Popen(cmd, cwd=backend_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)

def start_frontend():
    # Run npm run dev
    frontend_dir = os.path.join(os.getcwd(), 'frontend')
    # Using cmd.exe to run npm
    cmd = ["cmd.exe", "/c", "npm", "run", "dev"]
    return subprocess.Popen(cmd, cwd=frontend_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)

if __name__ == "__main__":
    print("Starting Auto Shorts Backend...")
    backend_process = start_backend()
    
    print("Starting Auto Shorts Frontend...")
    frontend_process = start_frontend()
    
    print("Waiting for servers to start...")
    time.sleep(3)
    
    print("Opening browser...")
    webbrowser.open("http://localhost:5173")
    
    print("\nServers are running in separate windows. Close this window to shut down both servers.")
    try:
        # Keep the launcher running until the user closes it manually
        while True:
            time.sleep(1)
            # If both processes died, exit
            if backend_process.poll() is not None and frontend_process.poll() is not None:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down...")
        backend_process.terminate()
        frontend_process.terminate()
