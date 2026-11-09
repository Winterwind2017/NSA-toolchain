"""COM 基础设施：错误类型、连接/文档基类、双栈桥接、选择标记、单位换算。"""
from .base import BaseCADApp          # noqa: F401
from .errors import (                 # noqa: F401
    AppNotRunningError, CadFrameworkError, ConnectionError, DocumentError,
    DrawingError, NotSupportedError,
)
