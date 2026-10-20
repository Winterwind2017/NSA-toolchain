"""
cad_framework.errors - Custom exception classes
"""


class CadFrameworkError(Exception):
    """Base exception for all CAD framework errors"""
    pass


class ConnectionError(CadFrameworkError):
    """Failed to connect to CAD application"""
    pass


class AppNotRunningError(CadFrameworkError):
    """CAD application is not running"""
    pass


class DocumentError(CadFrameworkError):
    """Document-related operation failed"""
    pass


class DrawingError(CadFrameworkError):
    """Drawing/creation operation failed"""
    pass


class NotSupportedError(CadFrameworkError):
    """Operation not supported for this CAD application"""
    pass
