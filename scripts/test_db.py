"""Run database checks in the dedicated ephemeral Compose test project."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "postgresql+psycopg://paleograph_test:paleograph_test@localhost:55432/paleograph_test"


def main() -> None:
    compose = [
        "docker",
        "compose",
        "-p",
        "paleograph-test",
        "-f",
        "docker-compose.test.yml",
    ]
    env = {**os.environ, "DATABASE_URL": URL, "TEST_DATABASE_URL": URL}
    alembic = [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini"]
    try:
        subprocess.run([*compose, "up", "-d", "--wait"], cwd=ROOT, check=True)
        for args in (
            ["upgrade", "head"],
            ["upgrade", "head"],
            ["downgrade", "base"],
            ["upgrade", "head"],
            ["check"],
        ):
            subprocess.run([*alembic, *args], cwd=ROOT, env=env, check=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *(sys.argv[1:] or ["apps/api/tests"]),
                "-m",
                "integration",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
    finally:
        subprocess.run([*compose, "down"], cwd=ROOT, check=False)


if __name__ == "__main__":
    main()
