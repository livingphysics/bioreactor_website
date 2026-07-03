"""
Pi camera snapshots for the bioreactor API.

Wraps `rpicam-still` to grab a single JPEG on demand. Self-contained — no
bioreactor_v3 / hardware dependency, and independent of HARDWARE_MODE (the CSI
camera is separate from the I2C/GPIO bus). Captures are serialized by a lock
because rpicam-still opens the camera exclusively.

The command is assembled as an argv list (never a shell string) from validated,
clamped numeric parameters, so query-param callers have no injection surface.
"""
import shutil
import logging
import threading
import subprocess

logger = logging.getLogger(__name__)

RPICAM_STILL = shutil.which("rpicam-still") or shutil.which("libcamera-still")
_capture_lock = threading.Lock()


class CameraError(Exception):
    """Raised when a camera capture cannot be produced."""


def available() -> bool:
    return RPICAM_STILL is not None


def capture_jpeg(*, width: int = 1280, height: int = 720, rotation: int = 0,
                 hflip: bool = False, vflip: bool = False, zoom: float = 1.0,
                 quality: int = 90, settle_ms: int = 800, timeout_s: float = 12.0) -> bytes:
    """Capture one JPEG frame and return the bytes. Raises CameraError on failure."""
    if not available():
        raise CameraError("rpicam-still not installed")

    width = max(64, min(int(width), 4608))
    height = max(64, min(int(height), 2592))
    quality = max(1, min(int(quality), 100))
    settle_ms = max(1, min(int(settle_ms), 5000))

    args = [RPICAM_STILL, "--nopreview", "-t", str(settle_ms), "-o", "-",
            "--width", str(width), "--height", str(height), "-q", str(quality),
            "--autofocus-mode", "auto"]
    if int(rotation) == 180:
        args += ["--rotation", "180"]
    if hflip:
        args += ["--hflip"]
    if vflip:
        args += ["--vflip"]
    try:
        zoom = float(zoom)
    except (TypeError, ValueError):
        zoom = 1.0
    if zoom > 1.0:
        zoom = min(zoom, 10.0)
        frac = 1.0 / zoom
        off = (1.0 - frac) / 2.0
        args += ["--roi", f"{off:.4f},{off:.4f},{frac:.4f},{frac:.4f}"]

    with _capture_lock:
        try:
            proc = subprocess.run(args, capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise CameraError("camera capture timed out")
        except OSError as e:
            raise CameraError(f"failed to run rpicam-still: {e}")

    if proc.returncode != 0 or not proc.stdout:
        lines = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise CameraError(lines[-1] if lines else f"rpicam-still exited {proc.returncode}")
    return proc.stdout
