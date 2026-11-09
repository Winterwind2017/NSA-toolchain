"""
cad_framework.base - BaseCADApp

Abstract base class providing:
- COM connection management (auto-detect / launch / reconnect)
- Context manager protocol (with statement)
- Common document operations interface
- Logging
"""

import abc
import sys
from datetime import datetime
from typing import Optional, Any, List

from .errors import ConnectionError, AppNotRunningError, DocumentError


class BaseCADApp(abc.ABC):
    """
    Base class for CAD application control via COM.
    Subclasses must define:
      - _progids: list of ProgID strings to try
      - _app_name: human-readable name for logging
    """

    _progids: List[str] = []
    _app_name: str = "GenericCAD"

    def __init__(self, visible: bool = True, log_to_stdout: bool = True):
        self._com_obj: Any = None
        self._used_progid: Optional[str] = None
        self._visible = visible
        self._connected = False
        self._log_to_stdout = log_to_stdout
        self._log_lines: List[str] = []

    # ─── Logging ──────────────────────────────────────────────

    def _log(self, level: str, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{self._app_name}] [{level}] {msg}"
        self._log_lines.append(line)
        if self._log_to_stdout:
            print(line, file=sys.stderr)  # stderr to avoid mixing with return values

    def get_logs(self) -> List[str]:
        return self._log_lines.copy()

    def clear_logs(self):
        self._log_lines.clear()

    # ─── Connection Management ────────────────────────────────

    @property
    def com_obj(self) -> Any:
        """Get the underlying COM object (raise if not connected)."""
        if not self._connected or self._com_obj is None:
            raise AppNotRunningError(f"{self._app_name} is not connected. Call connect() first.")
        return self._com_obj

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def app_name(self) -> str:
        return self._app_name

    @property
    def progid(self) -> Optional[str]:
        return self._used_progid

    def connect(self, force_launch: bool = False) -> bool:
        """
        Connect to the CAD application.
        Tries: 1) GetActiveObject (existing instance)
               2) Dispatch (launch new instance)

        Args:
            force_launch: If True, skip GetActiveObject and always launch new.
        """
        self._log("INFO", "Connecting...")

        try:
            import win32com.client
        except ImportError:
            raise ConnectionError("pywin32 not installed. Run: pip install pywin32")

        # Step 1: Try to get running instance
        if not force_launch:
            self._log("DEBUG", "Looking for running instance...")
            for pid in self._progids:
                try:
                    self._com_obj = win32com.client.GetActiveObject(pid)
                    self._used_progid = pid
                    self._connected = True
                    self._log("INFO", f"Connected to running instance: {pid}")
                    self._post_connect()
                    return True
                except Exception:
                    continue

        # Step 2: Launch new instance
        self._log("INFO", "Launching new instance...")
        for pid in self._progids[:5]:  # Limit attempts
            try:
                self._com_obj = win32com.client.Dispatch(pid)
                self._used_progid = pid
                self._connected = True
                self._log("INFO", f"Launched: {pid}")
                self._post_connect()
                return True
            except Exception as e:
                self._log("DEBUG", f"Failed with {pid}: {e}")
                continue

        raise ConnectionError(
            f"Cannot connect to {self._app_name}. "
            f"Tried ProgIDs: {self._progids}. "
            f"Ensure {self._app_name} is installed."
        )

    def _post_connect(self):
        """Hook called after successful connection. Override in subclasses."""
        if self._visible:
            try:
                self._com_obj.Visible = True
                self._log("DEBUG", "Set visible=True")
            except Exception:
                pass

    def disconnect(self):
        """Release COM object (does NOT quit the application)."""
        if self._com_obj is not None:
            self._com_obj = None
        self._connected = False
        self._log("INFO", "Disconnected")

    def quit_app(self):
        """Quit the CAD application."""
        try:
            self._com_obj.Quit()
            self._log("INFO", "Application quit")
        except Exception as e:
            self._log("WARN", f"Quit failed: {e}")
        finally:
            self._com_obj = None
            self._connected = False

    # ─── Context Manager ──────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    def __repr__(self):
        status = "connected" if self._connected else "disconnected"
        return f"<{self._app_name}({status}) progid={self._used_progid}>"

    # ─── Abstract Document Interface ──────────────────────────

    @abc.abstractmethod
    def new_document(self, template: Optional[str] = None):
        """Create a new document."""
        ...

    @abc.abstractmethod
    def open_document(self, filepath: str):
        """Open an existing document."""
        ...

    @abc.abstractmethod
    def save_document(self, filepath: Optional[str] = None):
        """Save the active document."""
        ...

    @abc.abstractmethod
    def close_document(self, save: bool = True):
        """Close the active document."""
        ...

    @abc.abstractmethod
    def export_pdf(self, filepath: str, **kwargs):
        """Export active document to PDF."""
        ...

    # ─── Abstract Drawing Primitives ──────────────────────────

    @abc.abstractmethod
    def draw_line(self, start, end):
        """Draw a line from start to end (2D or 3D)."""
        ...

    @abc.abstractmethod
    def draw_circle(self, center, radius):
        """Draw a circle."""
        ...

    @abc.abstractmethod
    def draw_rectangle(self, p1, p2):
        """Draw a rectangle defined by two corner points."""
        ...

    @abc.abstractmethod
    def draw_text(self, text: str, position, height: float):
        """Place text at a position."""
        ...

    # ─── Utility ──────────────────────────────────────────────

    def zoom_extents(self):
        """Zoom to the extents of the drawing."""
        try:
            self._com_obj.ZoomExtents()
        except Exception as e:
            self._log("WARN", f"ZoomExtents failed: {e}")
