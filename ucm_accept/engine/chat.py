from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..errors import ConnectionError
from .base import Endpoint, ProbeResult

_CONTEXT_KEYS = (
    "max_model_len",
    "max_context_length",
    "context_length",
    "context_window",
    "max_input_tokens",
)


@dataclass
class ChatResponse:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


def _extract_context(entry: dict[str, Any]) -> int | None:
    for key in _CONTEXT_KEYS:
        value = entry.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    for container in ("meta", "metadata", "config", "limits"):
        nested = entry.get(container)
        if isinstance(nested, dict):
            found = _extract_context(nested)
            if found:
                return found
    return None


class ChatClient:
    """极简 OpenAI 兼容客户端（标准库实现，便于离线与投标现场排障）。"""

    def __init__(self, endpoint: Endpoint):
        self.endpoint = endpoint

    # ------------------------------------------------------------------ http
    def _ssl_context(self) -> ssl.SSLContext | None:
        if self.endpoint.chat_url.startswith("https://") and not self.endpoint.verify_ssl:
            return ssl._create_unverified_context()  # noqa: S323 - 客户内网自签证书是常态
        return None

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        data = None
        headers = {"Accept": "application/json", "User-Agent": "ucm-accept/1.1"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.endpoint.api_key:
            headers["Authorization"] = f"Bearer {self.endpoint.api_key}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout or self.endpoint.timeout_s,
                context=self._ssl_context(),
            ) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return exc.code, dict(exc.headers or {}), body
        except urllib.error.URLError as exc:
            raise ConnectionError(f"无法连接服务 {url}：{exc.reason}") from exc
        except TimeoutError as exc:
            raise ConnectionError(f"连接服务超时（{timeout or self.endpoint.timeout_s}s）：{url}") from exc

    @staticmethod
    def _json(body: bytes) -> dict[str, Any]:
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # ----------------------------------------------------------------- model
    def list_models(self, timeout: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        status, _, body = self._request("GET", self.endpoint.models_url, timeout=timeout)
        parsed = self._json(body)
        if status != 200:
            detail = body.decode("utf-8", errors="replace")[:300]
            raise ConnectionError(f"/models 返回 HTTP {status}：{detail or '无响应内容'}")
        entries = parsed.get("data") or parsed.get("models") or []
        if not isinstance(entries, list):
            entries = []
        return [entry for entry in entries if isinstance(entry, dict)], parsed

    def find_context_window(self, entries: list[dict[str, Any]]) -> int | None:
        model = self.endpoint.model
        for entry in entries:
            if entry.get("id") == model or entry.get("model") == model:
                found = _extract_context(entry)
                if found:
                    return found
        if len(entries) == 1:
            return _extract_context(entries[0])
        for entry in entries:
            found = _extract_context(entry)
            if found:
                return found
        return None

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        started = time.perf_counter()
        status, _, body = self._request("POST", self.endpoint.chat_url, payload, timeout=timeout)
        latency_ms = (time.perf_counter() - started) * 1000
        parsed = self._json(body)
        if status != 200:
            detail = body.decode("utf-8", errors="replace")[:500]
            raise ConnectionError(f"对话请求失败（HTTP {status}）：{detail or '无响应内容'}")
        if "error" in parsed:
            raise ConnectionError(f"服务返回错误：{parsed['error']}")
        choices = parsed.get("choices") or []
        message = (choices[0] or {}).get("message", {}) if choices else {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        tool_calls = message.get("tool_calls") or []
        return ChatResponse(
            content=str(content),
            tool_calls=[call for call in tool_calls if isinstance(call, dict)],
            usage=parsed.get("usage") or {},
            latency_ms=latency_ms,
            raw=parsed,
        )

    # ----------------------------------------------------------------- probe
    def probe(self) -> ProbeResult:
        mode = self.endpoint.probe_mode or "auto"
        models: list[dict[str, Any]] = []
        context: int | None = None
        started = time.perf_counter()
        model_error = ""
        if mode in {"auto", "models"}:
            try:
                models, _ = self.list_models(timeout=self.endpoint.connect_timeout_s)
                context = self.find_context_window(models)
                elapsed = (time.perf_counter() - started) * 1000
                ids = [str(entry.get("id") or entry.get("model") or "") for entry in models]
                ids = [item for item in ids if item]
                if ids and self.endpoint.model not in ids:
                    message = f"服务连通，但模型列表中未找到 {self.endpoint.model}（共 {len(ids)} 个模型）"
                elif ids:
                    message = f"服务连通（{self.endpoint.model}）"
                else:
                    message = "服务连通（/models 未返回模型列表）"
                return ProbeResult(
                    connected=True,
                    message=message,
                    latency_ms=elapsed,
                    models=ids,
                    context_window=context,
                    detail=f"GET {self.endpoint.models_url}",
                )
            except ConnectionError as exc:
                model_error = str(exc)
                if mode == "models":
                    return ProbeResult(connected=False, message=model_error)

        try:
            response = self.chat(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                timeout=self.endpoint.connect_timeout_s,
            )
            elapsed = (time.perf_counter() - started) * 1000
            return ProbeResult(
                connected=True,
                message=f"服务连通（对话接口握手成功，{len(response.content)} 字符响应）",
                latency_ms=elapsed,
                models=[],
                context_window=context,
                detail=f"POST {self.endpoint.chat_url}",
            )
        except ConnectionError as exc:
            message = str(exc)
            if model_error:
                message = f"{model_error}；{message}"
            return ProbeResult(connected=False, message=message, latency_ms=None, models=[])

    def detect_context(self) -> int | None:
        try:
            models, _ = self.list_models(timeout=self.endpoint.connect_timeout_s)
        except ConnectionError:
            return None
        return self.find_context_window(models)
