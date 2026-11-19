from __future__ import annotations


class UCMAcceptError(RuntimeError):
    """工具层可预期错误，CLI/GUI 直接展示中文信息。"""


class ConfigError(UCMAcceptError):
    pass


class EngineError(UCMAcceptError):
    pass


class ConnectionError(UCMAcceptError):
    pass


class EvalScopeError(EngineError):
    pass


class EvalScopeNotFound(EvalScopeError):
    pass


class AssetError(UCMAcceptError):
    pass


class CancelledError(UCMAcceptError):
    pass


class ReportError(UCMAcceptError):
    pass


class PDFExportError(ReportError):
    pass
