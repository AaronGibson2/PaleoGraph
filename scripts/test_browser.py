"""Real Next.js -> typed client -> FastAPI -> disposable PostGIS browser validation."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
URL = "postgresql+psycopg://paleograph_browser:paleograph_browser@localhost:56432/paleograph_browser"


def ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "Validation server exited; see data/processed/browser-*.log"
            )
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"Validation server did not become ready: {url}")


def main() -> None:
    pnpm = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
    if not pnpm:
        raise RuntimeError("pnpm is required")
    compose = [
        "docker",
        "compose",
        "-p",
        "paleograph-browser",
        "-f",
        "docker-compose.browser.yml",
    ]
    env = {
        **os.environ,
        "DATABASE_URL": URL,
        "CORS_ORIGINS": '["http://localhost:3001"]',
        "NEXT_PUBLIC_API_BASE_URL": "http://localhost:8001/api/v1",
        "NEXT_DIST_DIR": ".next-e2e",
        "E2E_BASE_URL": "http://localhost:3001",
        "E2E_API_BASE_URL": "http://localhost:8001/api/v1",
    }
    processes: list[subprocess.Popen[bytes]] = []
    logs = []
    generated_files = [ROOT / "apps/web/tsconfig.json", ROOT / "apps/web/next-env.d.ts"]
    originals = {file: file.read_bytes() for file in generated_files}
    generated: dict[Path, bytes] = {}
    try:
        subprocess.run([*compose, "up", "-d", "--wait"], cwd=ROOT, check=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/api/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [sys.executable, "scripts/prepare_browser_db.py"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [pnpm, "--filter", "@paleograph/web", "build"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        generated = {file: file.read_bytes() for file in generated_files}
        logdir = ROOT / "data/processed"
        logdir.mkdir(exist_ok=True)
        for name, command, cwd, url in (
            (
                "api",
                [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8001"],
                ROOT / "apps/api",
                "http://localhost:8001/api/v1/health",
            ),
            (
                "web",
                [
                    shutil.which("node") or "node",
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--port",
                    "3001",
                ],
                ROOT / "apps/web",
                "http://localhost:3001/explore",
            ),
        ):
            log = (logdir / f"browser-{name}.log").open("wb")
            logs.append(log)
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            processes.append(process)
            ready(url, process)
        subprocess.run(
            [pnpm, "--filter", "@paleograph/web", "test:e2e"],
            cwd=ROOT,
            env=env,
            check=True,
        )
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
        for file, contents in generated.items():
            if file.read_bytes() == contents:
                file.write_bytes(originals[file])
        subprocess.run([*compose, "down"], cwd=ROOT, check=False)


if __name__ == "__main__":
    main()
