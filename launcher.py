import subprocess
import os
import sys
import webbrowser
import time
import socket

def get_open_port():
    """Finds an available open port on the system."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port

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
    backend_port = get_open_port()
    frontend_port = get_open_port()
    
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
