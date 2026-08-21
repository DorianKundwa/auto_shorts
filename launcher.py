import subprocess
import os
import sys
import webbrowser
import time
import socket


def get_open_port(preferred: int = 0) -> int:
    """
    Find an available TCP port.
    Fix #15: scan upward from 'preferred' (or use a random OS port if 0) so
    we pick a well-known port rather than a random ephemeral one.  Using a
    predictable port reduces (but cannot eliminate) the OS race between
    releasing the socket here and the child process binding to it.
    """
    start = preferred if preferred > 0 else 49152  # start of ephemeral range
    for port in range(start, start + 50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    # Absolute fallback: let the OS choose
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def start_backend(port):
    """Starts the FastAPI backend on the specified port."""
    backend_dir = os.path.join(os.getcwd(), 'backend')
    venv_python = os.path.join(backend_dir, 'venv', 'Scripts', 'python.exe')
    
    if not os.path.exists(venv_python):
        print("Backend virtual environment not found. Please ensure it is installed.")
        sys.exit(1)
        
    cmd = [venv_python, "-m", "uvicorn", "main:app", "--port", str(port)]
    return subprocess.Popen(cmd, cwd=backend_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)

def start_frontend(frontend_port, backend_port):
    """Starts the Vite frontend on the specified port and links it to the backend."""
    frontend_dir = os.path.join(os.getcwd(), 'frontend')
    
    # Inject backend API URL so the frontend knows where to connect dynamically
    env = os.environ.copy()
    env["VITE_API_URL"] = f"http://localhost:{backend_port}/api"
    
    # Run npm run dev and force it to use the selected open port
    cmd = ["cmd.exe", "/c", "npm", "run", "dev", "--", "--port", str(frontend_port), "--strictPort"]
    return subprocess.Popen(cmd, cwd=frontend_dir, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)

if __name__ == "__main__":
    print("Finding open ports...")
    backend_port = get_open_port(preferred=8000)
    frontend_port = get_open_port(preferred=5173)
    
    print(f"Assigning Backend -> Port {backend_port}")
    print(f"Assigning Frontend -> Port {frontend_port}\n")

    print("Starting Auto Shorts Backend...")
    backend_process = start_backend(backend_port)
    
    print("Starting Auto Shorts Frontend...")
    frontend_process = start_frontend(frontend_port, backend_port)
    
    print("Waiting for servers to start...")
    time.sleep(3)
    
    frontend_url = f"http://localhost:{frontend_port}"
    print(f"Opening browser to {frontend_url}...")
    webbrowser.open(frontend_url)
    
    print("\nServers are running in separate windows. Close this window to shut down both servers.")
    try:
        # Keep the launcher running until the user closes it manually
        while True:
            time.sleep(1)
            if backend_process.poll() is not None and frontend_process.poll() is not None:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down servers...")
        backend_process.terminate()
        frontend_process.terminate()
