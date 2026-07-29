"""
Setup utilities for capture system prerequisites.
Handles mitmproxy installation, certificate generation, and prerequisite checking.
"""

import subprocess
import ctypes
import time
import os
import sys
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def find_mitmdump() -> Optional[str]:
    """
    Find the mitmdump executable, checking multiple locations.

    When running from a bundled exe, mitmdump may not be on PATH.
    This function checks common installation locations.

    Returns:
        Path to mitmdump executable, or None if not found
    """
    # First try shutil.which (checks PATH)
    mitmdump_path = shutil.which("mitmdump")
    if mitmdump_path:
        return mitmdump_path

    # Common locations to check on Windows
    if sys.platform == "win32":
        locations_to_check = []

        # Check Python Scripts folders
        # When running bundled exe, sys.executable is the exe path
        # But we can still check common Python installation paths

        # User's Python Scripts folder
        user_scripts = Path.home() / "AppData" / "Local" / "Programs" / "Python"
        if user_scripts.exists():
            for python_dir in user_scripts.glob("Python*"):
                scripts_dir = python_dir / "Scripts"
                locations_to_check.append(scripts_dir / "mitmdump.exe")

        # System Python Scripts folders
        for base in [r"C:\Python", r"C:\Program Files\Python", r"C:\Program Files (x86)\Python"]:
            base_path = Path(base)
            if base_path.exists():
                for python_dir in base_path.glob("Python*"):
                    locations_to_check.append(python_dir / "Scripts" / "mitmdump.exe")

        # pyenv-win locations
        pyenv_root = Path.home() / ".pyenv" / "pyenv-win" / "versions"
        if pyenv_root.exists():
            for version_dir in pyenv_root.glob("*"):
                locations_to_check.append(version_dir / "Scripts" / "mitmdump.exe")

        # Check if running from bundled exe - look next to the exe
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            locations_to_check.append(exe_dir / "mitmdump.exe")

        # Try each location
        for path in locations_to_check:
            if path.exists():
                return str(path)

    return None


@dataclass
class PrerequisiteStatus:
    """Status of capture system prerequisites."""
    is_admin: bool
    has_mitmproxy: bool
    mitmproxy_version: Optional[str]
    has_certificate: bool
    certificate_path: Optional[Path]


def check_prerequisites() -> PrerequisiteStatus:
    """
    Check if all prerequisites for capture system are met.

    Returns:
        PrerequisiteStatus object with current status of all requirements
    """
    # Check admin privileges (Windows only)
    is_admin = False
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        pass

    # Check mitmproxy installation
    has_mitmproxy = False
    mitmproxy_version = None
    mitmdump_path = find_mitmdump()
    if mitmdump_path:
        try:
            # stdin closed and no console window: this runs under a GUI
            # process, where an inherited console makes a window flash
            # over the UI and a child waiting on input would sit out the
            # whole timeout. Callers must still run this off the UI
            # thread -- the timeout bounds the wait, it doesn't remove it.
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                )
            result = subprocess.run(
                [mitmdump_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
                **kwargs
            )
            if result.returncode == 0:
                has_mitmproxy = True
                # Extract version from output (e.g., "Mitmproxy 10.1.1")
                mitmproxy_version = result.stdout.split()[1] if result.stdout else "unknown"
        except (OSError, subprocess.SubprocessError):
            pass

    # Check certificate
    cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"
    has_certificate = cert_path.exists()

    return PrerequisiteStatus(
        is_admin=is_admin,
        has_mitmproxy=has_mitmproxy,
        mitmproxy_version=mitmproxy_version,
        has_certificate=has_certificate,
        certificate_path=cert_path if has_certificate else None
    )


def install_mitmproxy(timeout: int = 120) -> bool:
    """
    Install mitmproxy via pip.

    Args:
        timeout: Maximum time in seconds to wait for installation

    Returns:
        True if installation succeeded, False otherwise

    Raises:
        subprocess.TimeoutExpired: If installation takes longer than timeout
        Exception: If installation fails for other reasons
    """
    result = subprocess.run(
        ["pip", "install", "mitmproxy"],
        capture_output=True,
        text=True,
        timeout=timeout
    )

    if result.returncode != 0:
        raise Exception(f"Installation failed: {result.stderr}")

    return True


def setup_certificate() -> Path:
    """
    Generate mitmproxy CA certificate by starting and stopping mitmdump.

    Returns:
        Path to the generated certificate

    Raises:
        FileNotFoundError: If mitmdump is not installed
        Exception: If certificate generation fails
    """
    mitmdump_path = find_mitmdump()
    if not mitmdump_path:
        raise FileNotFoundError("mitmdump not found. Please install mitmproxy.")

    # Start mitmdump briefly to generate certificate
    process = subprocess.Popen(
        [mitmdump_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Give it time to generate the certificate
    time.sleep(3)

    # Stop the process
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

    # Verify certificate was created
    cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"
    if not cert_path.exists():
        raise Exception("Certificate was not generated")

    return cert_path


def open_certificate(cert_path: Path) -> None:
    """
    Open certificate file in Windows (for manual installation).

    Args:
        cert_path: Path to certificate file

    Raises:
        Exception: If unable to open certificate
    """
    if not cert_path.exists():
        raise FileNotFoundError(f"Certificate not found: {cert_path}")

    try:
        os.startfile(str(cert_path))
    except Exception as e:
        raise Exception(f"Failed to open certificate: {e}")
