from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "railway_direct_deploy.sh"


def run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=child_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_direct_deploy_requires_explicit_confirmation() -> None:
    result = run_script({"CONFIRM_DIRECT_RAILWAY_DEPLOY": ""})

    assert result.returncode == 1
    assert "CONFIRM_DIRECT_RAILWAY_DEPLOY=yes" in result.stderr


def test_direct_deploy_dry_run_does_not_require_railway_cli() -> None:
    result = run_script(
        {
            "CONFIRM_DIRECT_RAILWAY_DEPLOY": "yes",
            "DRY_RUN": "1",
            "PATH": "/usr/bin:/bin",
            "RAILWAY_SERVICE_NAME": "stratum-backend",
            "RAILWAY_ENVIRONMENT": "production",
            "DEPLOY_MESSAGE": "test direct deploy",
        }
    )

    assert result.returncode == 0
    assert "Dry run only" in result.stdout
    assert "railway up" in result.stdout
    assert "deployment status" in result.stdout
    assert "live_backend_smoke.py" in result.stdout
