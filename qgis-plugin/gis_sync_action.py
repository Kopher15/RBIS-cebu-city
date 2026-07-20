import subprocess
from pathlib import Path
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface
from qgis.core import QgsMessageLog, Qgis

POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
SYNC_SCRIPT = r"C:\gis-sync\scripts\run-sync.ps1"
# Canonical RBIS repo — export + git push (Vercel auto-deploys from main)
PUSH_SCRIPT = r"E:\Work\App Projects\context\Projects\RBIS-cebu-city\push-update.ps1"


def _run_ps1(script_path, timeout_sec):
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", script_path,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )


def _summarize_sync(stdout):
    summary_parts = []
    for line in stdout.splitlines():
        s = line.strip()
        for prefix in ("run_id", "inserted", "updated", "soft_deleted", "un_deleted", "elapsed"):
            if s.startswith(prefix):
                summary_parts.append(" ".join(s.split()))
                break
    return " | ".join(summary_parts) if summary_parts else "Sync completed"


def run_sync():
    """PostGIS sync, then export GeoJSON and push so the Vercel dashboard updates."""
    if not Path(SYNC_SCRIPT).exists():
        iface.messageBar().pushCritical(
            "Sync failed",
            f"Script not found: {SYNC_SCRIPT}",
        )
        return

    bar = iface.messageBar()
    bar.clearWidgets()
    bar.pushInfo("Sync running", "PostGIS sync starting...")
    QApplication.processEvents()

    try:
        result = _run_ps1(SYNC_SCRIPT, timeout_sec=120)
    except Exception as e:
        bar.clearWidgets()
        bar.pushCritical("Sync failed", f"Exception: {e}")
        QgsMessageLog.logMessage(f"exception: {e}", "gis_sync", Qgis.Critical)
        return

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode != 0:
        bar.clearWidgets()
        detail = (stderr or stdout).strip().replace("\n", " | ")
        if len(detail) > 200:
            detail = detail[:200] + "..."
        bar.pushCritical(f"Sync failed (exit {result.returncode})", detail or "See logs")
        QgsMessageLog.logMessage(
            f"rc={result.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}",
            "gis_sync",
            Qgis.Critical,
        )
        return

    QgsMessageLog.logMessage(f"postgis rc=0\n{stdout}", "gis_sync", Qgis.Info)
    sync_summary = _summarize_sync(stdout)

    if not Path(PUSH_SCRIPT).exists():
        bar.clearWidgets()
        bar.pushCritical(
            "PostGIS synced, publish skipped",
            f"Publish script not found: {PUSH_SCRIPT}",
        )
        QgsMessageLog.logMessage(
            f"PostGIS OK but push script missing: {PUSH_SCRIPT}",
            "gis_sync",
            Qgis.Warning,
        )
        return

    bar.clearWidgets()
    bar.pushInfo("Publishing", "Exporting GeoJSON and pushing to GitHub/Vercel...")
    QApplication.processEvents()

    try:
        push = _run_ps1(PUSH_SCRIPT, timeout_sec=300)
    except Exception as e:
        bar.clearWidgets()
        bar.pushCritical("PostGIS synced, publish failed", f"Exception: {e}")
        QgsMessageLog.logMessage(f"publish exception: {e}", "gis_sync", Qgis.Critical)
        return

    push_out = push.stdout or ""
    push_err = push.stderr or ""
    QgsMessageLog.logMessage(
        f"publish rc={push.returncode}\nstdout:\n{push_out}\nstderr:\n{push_err}",
        "gis_sync",
        Qgis.Info if push.returncode == 0 else Qgis.Critical,
    )

    bar.clearWidgets()
    if push.returncode == 0:
        bar.pushSuccess(
            "Sync + publish complete",
            f"{sync_summary} | Dashboard publishing to Vercel",
        )
    else:
        detail = (push_err or push_out).strip().replace("\n", " | ")
        if len(detail) > 200:
            detail = detail[:200] + "..."
        bar.pushCritical(
            f"PostGIS synced, publish failed (exit {push.returncode})",
            detail or "See Log Messages → gis_sync",
        )
