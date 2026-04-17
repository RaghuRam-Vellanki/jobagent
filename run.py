#!/usr/bin/env python3
"""
JobAgent v2 — Universal launcher (works on Windows cmd, PowerShell, Git Bash, Mac, Linux)
Usage: python run.py
"""
import subprocess, sys, os, time, signal, socket, shutil

# Force UTF-8 output so ✓/✗ render on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv")
FRONTEND = os.path.join(ROOT, "frontend")

# ── Colours ────────────────────────────────────────────────────────────
def green(s):  return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def cyan(s):   return f"\033[36m{s}\033[0m"

def step(n, msg): print(f"  [{n}/5] {yellow(msg)}")
def ok(msg):      print(f"        {green('✓')} {msg}")
def err(msg):     print(f"        {red('✗')} {msg}")

# ── Helpers ────────────────────────────────────────────────────────────

def is_port_free(port):
    # Try both IPv4 and IPv6 — Vite binds to ::1 on some Windows setups
    for host in ("127.0.0.1", "::1"):
        try:
            af = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(af) as s:
                if s.connect_ex((host, port)) == 0:
                    return False
        except OSError:
            pass
    return True

def kill_port(port):
    """Kill whatever is listening on `port` (Windows + Unix)."""
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                f'netstat -ano | findstr ":{port} "', shell=True
            ).decode()
            for line in out.splitlines():
                parts = line.split()
                if parts and parts[-1].isdigit():
                    subprocess.call(f"taskkill /F /PID {parts[-1]}", shell=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    else:
        subprocess.call(f"fuser -k {port}/tcp", shell=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_for_port(port, timeout=20):
    for _ in range(timeout * 2):
        if not is_port_free(port):
            return True
        time.sleep(0.5)
    return False

def python_bin():
    """Python executable inside venv."""
    if sys.platform == "win32":
        return os.path.join(VENV, "Scripts", "python.exe")
    return os.path.join(VENV, "bin", "python")

def pip_bin():
    if sys.platform == "win32":
        return os.path.join(VENV, "Scripts", "pip.exe")
    return os.path.join(VENV, "bin", "pip")

# ── Steps ──────────────────────────────────────────────────────────────

def ensure_venv():
    step(1, "Python virtual environment")
    if not os.path.exists(python_bin()):
        subprocess.check_call([sys.executable, "-m", "venv", VENV])
    ok(f"venv at {VENV}")

def install_python_deps():
    step(2, "Python dependencies")
    req = os.path.join(ROOT, "backend", "requirements.txt")
    subprocess.check_call([pip_bin(), "install", "-q", "-r", req])
    # Playwright browsers (show progress — first install is ~200 MB download)
    pw_result = subprocess.call([python_bin(), "-m", "playwright", "install", "chromium"])
    if pw_result != 0:
        err("Playwright install failed — run manually: python -m playwright install chromium")
    ok("backend deps installed")

def install_node_deps():
    step(3, "Node dependencies")
    if not os.path.exists(os.path.join(FRONTEND, "node_modules", "vite")):
        npm = shutil.which("npm")
        if not npm:
            err("npm not found — install Node.js from https://nodejs.org")
            sys.exit(1)
        subprocess.check_call([npm, "install", "--silent"], cwd=FRONTEND)
    ok("node deps installed")

def copy_env():
    step(4, ".env file")
    env_path = os.path.join(ROOT, ".env")
    example  = os.path.join(ROOT, ".env.example")
    if not os.path.exists(env_path):
        shutil.copy(example, env_path)
        ok("created .env from .env.example")
    else:
        ok(".env exists")

def launch():
    step(5, "Starting servers")

    # Clear ports
    for port in (8000, 5173):
        if not is_port_free(port):
            print(f"        Clearing port {port}...")
            kill_port(port)
            time.sleep(1)

    # Backend — use serve.py so ProactorEventLoop is set before uvicorn starts
    # (Playwright needs ProactorEventLoop to spawn subprocesses on Windows)
    backend_env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "backend")}
    backend = subprocess.Popen(
        [python_bin(), os.path.join(ROOT, "backend", "serve.py")],
        cwd=ROOT,
        env=backend_env,
    )

    print("        Waiting for backend...", end="", flush=True)
    if wait_for_port(8000, timeout=20):
        print(f" {green('ready')}")
    else:
        print(f" {red('timeout — check terminal for errors')}")
        backend.terminate()
        sys.exit(1)

    # Frontend
    npm = shutil.which("npm") or "npm"
    frontend = subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND)

    print("        Waiting for frontend...", end="", flush=True)
    if wait_for_port(5173, timeout=20):
        print(f" {green('ready')}")
    else:
        print(f" {red('timeout — check terminal for errors')}")

    print()
    print(cyan("  ============================================"))
    print(cyan("     JobAgent v2 is running!"))
    print(cyan("  ============================================"))
    print(f"  Dashboard  -->  {green('http://localhost:5173')}")
    print(f"  API docs   -->  {green('http://localhost:8000/docs')}")
    print()
    print("  Press  Ctrl+C  to stop both servers.")
    print()

    # Open browser
    try:
        import webbrowser
        webbrowser.open("http://localhost:5173")
    except Exception:
        pass

    # Wait and forward Ctrl+C
    def shutdown(sig, frame):
        print("\n  Stopping servers...")
        backend.terminate()
        frontend.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Watch both processes — restart backend if it crashes
    while True:
        time.sleep(2)
        if backend.poll() is not None:
            print(f"\n  {red('Backend stopped (exit=%d) — restarting...' % backend.returncode)}")
            time.sleep(1)
            backend = subprocess.Popen(
                [python_bin(), os.path.join(ROOT, "backend", "serve.py")],
                cwd=ROOT,
                env=backend_env,
            )
            if wait_for_port(8000, timeout=15):
                print(f"  {green('Backend restarted.')}")
            else:
                print(f"  {red('Backend failed to restart — check for errors above.')}")
        if frontend.poll() is not None:
            print(f"\n  {yellow('Frontend stopped — restarting...')}")
            npm = shutil.which("npm") or "npm"
            frontend = subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND)
            if wait_for_port(5173, timeout=15):
                print(f"  {green('Frontend restarted.')}")

# ── Main ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print(cyan("  =========================================="))
    print(cyan("     JobAgent v2  --  LazyApply"))
    print(cyan("  =========================================="))
    print()
    try:
        ensure_venv()
        install_python_deps()
        install_node_deps()
        copy_env()
        launch()
    except KeyboardInterrupt:
        print("\n  Aborted.")
    except subprocess.CalledProcessError as e:
        err(f"Command failed: {e}")
        sys.exit(1)
