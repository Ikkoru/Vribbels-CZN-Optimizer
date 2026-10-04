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

    cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"

    # Start mitmdump; it writes the CA into ~/.mitmproxy on first run.
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [mitmdump_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        **kwargs
    )

    try:
        # Wait for the certificate to appear rather than for a fixed
        # duration: it's usually written in well under a second, and a
        # fixed wait is both slower than it needs to be and too short
        # whenever a cold start or an antivirus scan delays the write.
        # Non-zero size, since the file is visible before it's complete.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if cert_path.exists() and cert_path.stat().st_size > 0:
                break
            if process.poll() is not None:
                # mitmdump exited on its own (bad install, port in use);
                # nothing more is coming.
                break
            time.sleep(0.1)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    # Verify certificate was created
    if not cert_path.exists():
        raise Exception("Certificate was not generated")

    return cert_path


# What mitmproxy's CA is called in a certificate store, and the files
# under ~/.mitmproxy holding it. `mitmproxy-ca.pem` and `mitmproxy-ca.p12`
# carry the PRIVATE KEY; the `-cert` files are the certificate alone.
CERT_NAME = "mitmproxy"
CA_FILES = ("mitmproxy-ca.pem", "mitmproxy-ca.p12", "mitmproxy-ca-cert.pem",
            "mitmproxy-ca-cert.cer", "mitmproxy-ca-cert.p12")
# The trusted-root stores the import wizard offers, with certutil's flag
# for each: the instructions say Local Machine, and Current User is
# where the wizard puts it if that step is missed.
CERT_STORES = (("Local Machine", []), ("Current User", ["-user"]))
# How many times a store is asked to give up a certificate of that name
# before it is reported as refusing. Each Generate that made a new CA
# can have left one behind.
CERT_DELETE_TRIES = 10


@dataclass
class CertificateRemoval:
    """What `remove_certificate` did: the stores the CA was taken out
    of, the files deleted, and every step that failed, as (where, why)."""
    stores: list
    files: list
    failures: list


def _certutil(args, timeout=15):
    """Run certutil with no console window and nothing on stdin."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(["certutil"] + list(args), capture_output=True,
                          text=True, errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL, **kwargs)


def _in_store(flags) -> bool:
    """Whether a store's trusted roots hold a certificate of
    `CERT_NAME`. Read-only: certutil answers 0 when it finds one."""
    try:
        return _certutil(list(flags) + ["-store", "Root", CERT_NAME]
                         ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def remove_certificate(confdir=None) -> CertificateRemoval:
    """Take every mitmproxy CA out of the trusted roots, and delete the
    files holding the current one and its key.

    **Both, because each closes a different door.** Out of the stores,
    Windows no longer trusts what the key signs, wherever a copy of the
    key went. With the files gone, the next `setup_certificate` makes a
    NEW key: left in place, Generate & Install Cert would install the
    very CA being withdrawn.

    Every certificate named `CERT_NAME` goes, not only the current
    file's: a CA from an earlier Generate is trusted as much as this
    one. Current User's store puts up Windows' own prompt before it
    deletes; Local Machine's needs Administrator, which capturing
    already runs as. The rest of ~/.mitmproxy -- mitmproxy's settings,
    `mitmproxy-dhparam.pem` -- is left alone.
    """
    out = CertificateRemoval([], [], [])
    for store, flags in CERT_STORES:
        removed = False
        for _ in range(CERT_DELETE_TRIES):
            if not _in_store(flags):
                break
            try:
                done = _certutil(list(flags) + ["-delstore", "Root",
                                                CERT_NAME], timeout=120)
            except (OSError, subprocess.SubprocessError) as e:
                out.failures.append((store, str(e)))
                break
            if done.returncode != 0:
                said = (done.stdout or done.stderr or "").strip().splitlines()
                out.failures.append(
                    (store, said[-1] if said else
                     "certutil exited with %d" % done.returncode))
                break
            removed = True
        else:
            if _in_store(flags):
                out.failures.append(
                    (store, "a certificate named %s is still there after "
                     "%d deletions" % (CERT_NAME, CERT_DELETE_TRIES)))
        if removed:
            out.stores.append(store)
    folder = Path(confdir) if confdir else Path.home() / ".mitmproxy"
    for name in CA_FILES:
        path = folder / name
        if not path.exists():
            continue
        try:
            path.unlink()
            out.files.append(name)
        except OSError as e:
            out.failures.append((name, str(e)))
    return out


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
