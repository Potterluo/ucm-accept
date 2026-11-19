from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from .config import Config
from .engine.base import (
    AccuracyParams,
    AgentParams,
    Endpoint,
    Engine,
    MultiturnParams,
    PerfParams,
    SlaNativeParams,
)
from .errors import CancelledError, UCMAcceptError
from .events import ProgressCallback, emit
from .models import (
    ITEM_BY_KEY,
    ITEM_KEYS,
    AcceptanceReport,
    AccuracyDataset,
    AccuracyDetail,
    AccuracyRun,
    ItemResult,
    SlaDetail,
    SlaTarget,
    Status,
    human_duration,
    iso_now,
    percent,
)
from .report import render_report
from .utils import ensure_dir, new_run_id, relative_artifact, set_latest_pointer, write_json_atomic

# 兼容“精度数据集配置里没有显式 limit”的情况
_FALLBACK_LIMIT = 100


class Orchestrator:
    """五项验收测试的编排器；同一实例顺序执行，不并发调用引擎。"""

    def __init__(
        self,
        config: Config,
        engine: Engine,
        *,
        outputs_root: str | Path | None = None,
        run_id: str | None = None,
        progress: ProgressCallback | None = None,
    ):
        self.config = config
        self.engine = engine
        self.progress = progress
        self.run_id = run_id or new_run_id()
        root = Path(outputs_root) if outputs_root else config.report_dir
        self.outputs_root = ensure_dir(root)
        self.run_dir = ensure_dir(self.outputs_root / "runs" / self.run_id)
        self.raw_root = ensure_dir(self.run_dir / "evalscope")
        self.item_dir = ensure_dir(self.run_dir / "items")
        self.log_path = self.run_dir / "run.log"
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._busy = False
        self._fraction = 0.0
        self._overall_base = 0.0
        self._overall_span = 1.0
        self._current: ItemResult | None = None
        endpoint = self._endpoint()
        self.report = AcceptanceReport(
            run_id=self.run_id,
            mode=engine.mode,
            endpoint=endpoint.to_public_dict(),
            started_at=iso_now(),
            config_snapshot=config.masked(),
            output_dir=str(self.run_dir),
            title=str(config.get("report.title", "UCM 推理加速产品验收报告")),
        )
        self._append_log(f"验收任务 {self.run_id} 启动（{engine.mode} 模式）")
        self.write_outputs()

    # ---------------------------------------------------------------- helpers
    def _endpoint(self) -> Endpoint:
        return Endpoint(
            base_url=str(self.config.get("endpoint.base_url")),
            model=str(self.config.get("endpoint.model")),
            api_key=str(self.config.get("endpoint.api_key", "") or ""),
            timeout_s=float(self.config.get("endpoint.timeout_s", 180)),
            connect_timeout_s=float(self.config.get("endpoint.connect_timeout_s", 8)),
            verify_ssl=bool(self.config.get("endpoint.verify_ssl", False)),
            probe_mode=str(self.config.get("endpoint.probe_mode", "auto")),
        )

    def _tokenizer(self) -> str:
        raw = str(self.config.get("perf.tokenizer_path", "") or "").strip()
        if not raw:
            return ""
        candidate = self.config.resolve_asset(raw)
        if candidate.exists():
            return str(candidate)
        if raw.startswith(("/", "./", "../", "~")):
            return str(candidate)
        return raw

    def _append_log(self, message: str) -> None:
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(message.rstrip() + "\n")
        except OSError:
            pass

    def _emit(self, message: str, *, level: str = "info", fraction: float | None = None) -> None:
        if fraction is not None:
            self._fraction = max(0.0, min(1.0, fraction))
        overall = self._overall_base + self._overall_span * self._fraction
        emit(
            self.progress,
            self._current.key if self._current else "",
            message,
            fraction=self._fraction,
            overall=overall,
            level=level,
        )
        self._append_log(f"[{self._current.key if self._current else 'run'}] {message}")

    def _log_fn(self):
        def log(message: str) -> None:
            if self._current is not None:
                self._current.logs.append(message)
                if len(self._current.logs) > 400:
                    del self._current.logs[:100]
            self._emit(message, level="command" if message.startswith("[EvalScope]") else "info")

        return log

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise CancelledError("用户已取消")

    def cancel(self) -> None:
        self.cancel_event.set()
        self._append_log("收到取消请求")

    # ------------------------------------------------------------ public runs
    def run_item(self, key: str, *, scenario: str | None = None) -> ItemResult:
        if key not in ITEM_BY_KEY:
            raise UCMAcceptError(f"未知测试项：{key}")
        if not self._lock.acquire(blocking=False):
            raise UCMAcceptError("已有验收任务正在执行，请等待完成")
        try:
            self._busy = True
            self.cancel_event.clear()
            self._overall_base = 0.0
            self._overall_span = 1.0
            return self._execute_one(key, scenario=scenario)
        finally:
            self._busy = False
            self._lock.release()

    def run_all(self) -> AcceptanceReport:
        if not self._lock.acquire(blocking=False):
            raise UCMAcceptError("已有验收任务正在执行，请等待完成")
        try:
            self._busy = True
            self.cancel_event.clear()
            total = len(ITEM_KEYS)
            for index, key in enumerate(ITEM_KEYS):
                self._check_cancel()
                self._overall_base = index / total
                self._overall_span = 1 / total
                self._execute_one(key)
                if self.cancel_event.is_set():
                    break
            self._overall_base = 0.0
            self._overall_span = 1.0
            self.report.finalize()
            self.write_outputs()
            return self.report
        finally:
            self._busy = False
            self._lock.release()

    def current_report(self) -> AcceptanceReport:
        self.report.finalize()
        return self.report

    # ---------------------------------------------------------------- execute
    def _execute_one(self, key: str, *, scenario: str | None = None) -> ItemResult:
        meta = ITEM_BY_KEY[key]
        item = ItemResult(key=key, name=meta.name, status=Status.RUNNING, started_at=iso_now())
        self.report.items[key] = item
        self._current = item
        self._fraction = 0.0
        started = time.monotonic()
        self._emit(f"开始 {meta.name}", level="start")
        self._append_log(f"===== {meta.name} 开始 =====")
        handler = getattr(self, f"_run_{key}")
        try:
            handler(item, scenario=scenario)
            if item.status == Status.RUNNING:
                item.status = Status.PASSED
        except CancelledError:
            item.status = Status.SKIPPED
            item.summary = "用户取消，未完成该项验收"
            item.error = "canceled"
            self._emit(item.summary, level="warning")
        except Exception as exc:  # noqa: BLE001 - 交付工具必须把异常转为可读结果
            item.status = Status.FAILED
            item.error = str(exc)
            item.summary = str(exc).splitlines()[0][:240] or "执行失败"
            trace_path = self.run_dir / "logs" / f"{key}.traceback.txt"
            ensure_dir(trace_path.parent)
            trace_path.write_text(traceback.format_exc(), encoding="utf-8")
            self._emit(f"{meta.name} 执行失败：{item.summary}", level="error")
            item.artifacts["异常堆栈"] = relative_artifact(trace_path, self.run_dir)
        finally:
            item.duration_s = round(time.monotonic() - started, 2)
            item.finished_at = iso_now()
            if len(item.logs) > 200:
                item.logs = item.logs[-200:]
            write_json_atomic(self.item_dir / f"{key}.json", item.to_dict())
            self.report.finalize()
            self.write_outputs()
            self._append_log(
                f"===== {meta.name} 结束：{item.status.value}，耗时 {human_duration(item.duration_s)} ====="
            )
            self._current = None
        return item

    # ------------------------------------------------------------------- perf
    def _perf_params(self, *, parallel: list[int] | None = None, number: int | None = None) -> PerfParams:
        context = int(self.config.get("defaults.context_length", 65536))
        min_prompt = int(self.config.get("perf.min_prompt_length", context))
        max_prompt = int(self.config.get("perf.max_prompt_length", context))
        hit_rate = float(self.config.get("defaults.hit_rate", 0.0) or 0.0)
        prefix_length = int(round(max_prompt * max(0.0, min(1.0, hit_rate)))) if hit_rate > 0 else 0
        return PerfParams(
            parallel=list(parallel or self.config.get("perf.parallel", [20])),
            number=int(number or self.config.get("perf.number", 200)),
            min_prompt_length=min_prompt,
            max_prompt_length=max_prompt,
            min_tokens=int(self.config.get("perf.min_tokens", 256)),
            max_tokens=int(self.config.get("perf.max_tokens", 256)),
            prefix_length=prefix_length,
            tokenizer_path=self._tokenizer(),
            warmup_num=int(self.config.get("perf.warmup_num", 0)),
            request_timeout_s=int(self.config.get("perf.request_timeout_s", 21600)),
            dataset=str(self.config.get("perf.dataset", "random")),
            extra_args=[str(arg) for arg in (self.config.get("perf.extra_args", []) or [])],
            context_length=context,
        )

    def _run_perf(self, item: ItemResult, *, scenario: str | None = None) -> None:
        params = self._perf_params()
        output_dir = ensure_dir(self.raw_root / "perf")
        log = self._log_fn()
        self._emit(
            f"调用 EvalScope perf：并发 {params.parallel}，请求 {params.number}，"
            f"输入 {params.max_prompt_length} tokens",
            level="info",
            fraction=0.05,
        )
        detail = self.engine.run_perf(self._endpoint(), params, output_dir, log, self.cancel_event)
        self._set_detail(item, detail.to_dict())
        self._attach_command(item, output_dir)
        item.artifacts["原始输出目录"] = relative_artifact(output_dir, self.run_dir)
        summary_file = output_dir / "ucm_perf.json"
        if summary_file.exists():
            item.artifacts["归一化指标"] = relative_artifact(summary_file, self.run_dir)
        self._collect_native_artifacts(item, output_dir)
        threshold = float(self.config.get("perf.success_threshold", 0.99))
        rates = [point.success_rate for point in detail.points]
        primary = detail.primary
        if not detail.points:
            item.status = Status.FAILED
            item.summary = "未获得任何性能指标"
            return
        if min(rates) <= 0:
            item.status = Status.FAILED
            item.summary = "压测请求全部失败，请检查服务状态与模型名称"
        elif min(rates) < threshold:
            item.status = Status.WARNING
            item.summary = f"压测成功率 {percent(min(rates))}，低于阈值 {percent(threshold)}"
        else:
            item.status = Status.PASSED
            item.summary = (
                f"{primary.concurrency} 并发：吞吐 {primary.throughput_tok_s:.0f} tok/s，"
                f"TTFT.P90 {primary.ttft_p90_ms / 1000:.2f}s，TPOT.P90 {primary.tpot_p90_ms:.1f}ms，"
                f"成功率 {percent(min(rates))}"
            )
        if len(detail.points) > 1:
            item.summary += f"；已完成 {len(detail.points)} 个并发梯度"
        self._emit(item.summary, level="success" if item.status == Status.PASSED else "warning", fraction=1.0)

    # -------------------------------------------------------------- multiturn
    def _run_multiturn(self, item: ItemResult, *, scenario: str | None = None) -> None:
        key = scenario or str(self.config.get("multiturn.scenario", "dialogue"))
        presets = self.config.get("multiturn.scenarios", {}) or {}
        if key not in presets:
            raise UCMAcceptError(f"未知多轮对话预设：{key}")
        preset = presets[key]
        dataset_path = self.config.resolve_asset(preset.get("dataset_path", ""))
        params = MultiturnParams(
            scenario_key=key,
            scenario_label=str(preset.get("label", key)),
            dataset_path=dataset_path,
            parallel=int(self.config.get("multiturn.parallel", 4)),
            conversations=int(self.config.get("multiturn.conversations", 12)),
            min_turns=int(self.config.get("multiturn.min_turns", 2)),
            max_turns=int(self.config.get("multiturn.max_turns", 5)),
            min_tokens=int(self.config.get("multiturn.min_tokens", 128)),
            max_tokens=int(self.config.get("multiturn.max_tokens", 512)),
            request_timeout_s=int(self.config.get("multiturn.request_timeout_s", 180)),
            extra_args=[str(arg) for arg in (self.config.get("multiturn.extra_args", []) or [])],
        )
        output_dir = ensure_dir(self.raw_root / "multiturn" / key)
        self._emit(
            f"多轮场景「{params.scenario_label}」：{params.conversations} 组会话、"
            f"{params.parallel} 并发",
            fraction=0.05,
        )
        detail = self.engine.run_multiturn(self._endpoint(), params, output_dir, self._log_fn(), self.cancel_event)
        self._set_detail(item, detail.to_dict())
        self._attach_command(item, output_dir)
        item.artifacts["原始输出目录"] = relative_artifact(output_dir, self.run_dir)
        summary_file = output_dir / "ucm_multiturn.json"
        if summary_file.exists():
            item.artifacts["归一化结果"] = relative_artifact(summary_file, self.run_dir)
        self._collect_native_artifacts(item, output_dir)
        completion = detail.completion_rate
        if completion <= 0:
            item.status = Status.FAILED
            item.summary = "多轮会话全部失败"
        elif completion < 0.99:
            item.status = Status.WARNING
            item.summary = f"多轮会话完成率 {percent(completion)}"
        else:
            item.status = Status.PASSED
            item.summary = (
                f"{params.scenario_label}场景：{detail.load_total_conversations} 组会话、"
                f"{detail.total_turns} 轮，完成率 {percent(completion)}，"
                f"平均延迟 {detail.avg_latency_ms / 1000:.2f}s"
            )
            if detail.cache_hit_rate is not None:
                item.summary += f"，缓存命中 {percent(detail.cache_hit_rate)}"
        self._emit(item.summary, level="success" if item.status == Status.PASSED else "warning", fraction=1.0)

    # -------------------------------------------------------------------- SLA
    def _run_sla(self, item: ItemResult, *, scenario: str | None = None) -> None:
        target = SlaTarget(
            context_length=int(self.config.get("sla.target.context_length", 65536)),
            concurrency=int(self.config.get("sla.target.concurrency", 200)),
            ttft_p90_ms=float(self.config.get("sla.target.ttft_p90_ms", 10000)),
            tpot_p90_ms=float(self.config.get("sla.target.tpot_p90_ms", 50)),
        )
        output_dir = ensure_dir(self.raw_root / "sla")
        mode = str(self.config.get("sla.mode", "verify"))
        if mode == "auto_tune":
            params = SlaNativeParams(
                target_context=target.context_length,
                upper=int(self.config.get("sla.auto_tune.upper", target.concurrency)),
                lower=int(self.config.get("sla.auto_tune.lower", 2)),
                ttft_p90_ms=target.ttft_p90_ms,
                tpot_p90_ms=target.tpot_p90_ms,
                number=max(1, int(self.config.get("sla.verify.number", 200))),
                num_runs=int(self.config.get("sla.auto_tune.num_runs", 1)),
                number_multiplier=float(self.config.get("sla.auto_tune.number_multiplier", 2)),
                tokenizer_path=self._tokenizer(),
                variable=str(self.config.get("sla.auto_tune.variable", "parallel")),
                extra_args=[str(arg) for arg in (self.config.get("sla.auto_tune.extra_args", []) or [])],
            )
            self._emit("调用 EvalScope `perf --sla-auto-tune`（原生 p90_ttft / p90_tpot）…", fraction=0.05)
            detail = self.engine.run_sla_native(
                self._endpoint(), params, output_dir, self._log_fn(), self.cancel_event
            )
        else:
            number = int(self.config.get("sla.verify.number", 200))
            params = self._perf_params(parallel=[target.concurrency], number=number)
            params.min_prompt_length = target.context_length
            params.max_prompt_length = target.context_length
            params.min_tokens = 256
            params.max_tokens = 256
            params.warmup_num = int(self.config.get("sla.verify.warmup_num", 0))
            self._emit(
                f"调用 EvalScope perf 在 {target.concurrency} 并发、{target.context_length} 上下文下实测 P90 "
                f"（请求 {number}）…",
                fraction=0.05,
            )
            perf = self.engine.run_perf(
                self._endpoint(), params, output_dir / "verify", self._log_fn(), self.cancel_event
            )
            point = next(
                (candidate for candidate in perf.points if candidate.concurrency == target.concurrency),
                max(perf.points, key=lambda candidate: candidate.concurrency) if perf.points else None,
            )
            target_met = bool(point and point.meets(target.ttft_p90_ms, target.tpot_p90_ms))
            gaps: list[str] = []
            if point is None:
                gaps = ["未获得目标并发下的有效压测数据"]
            else:
                if point.ttft_p90_ms >= target.ttft_p90_ms:
                    gaps.append(
                        f"TTFT.P90 实测 {point.ttft_p90_ms / 1000:.2f}s，"
                        f"未达到 <{target.ttft_p90_ms / 1000:.2f}s"
                    )
                if point.tpot_p90_ms >= target.tpot_p90_ms:
                    gaps.append(
                        f"TPOT.P90 实测 {point.tpot_p90_ms:.1f}ms，"
                        f"未达到 <{target.tpot_p90_ms:.1f}ms"
                    )
            detail = SlaDetail(
                target=target,
                strategy="verify",
                target_met=target_met,
                satisfiable=target_met,
                recommended_concurrency=target.concurrency if target_met else None,
                probes=[point] if point else [],
                best=point if target_met else None,
                gaps=gaps,
                note=(
                    f"直接采用 EvalScope perf 在 {target.concurrency} 并发的实测 P90 判定，"
                    "未做任何自研并发搜索；如需建议并发，可切换到 auto_tune 模式。"
                ),
                output_dir=str(output_dir / "verify"),
            )
            write_json_atomic(output_dir / "verify" / "ucm_sla.json", detail.to_dict())
        self._set_detail(item, detail.to_dict())
        self._attach_command(item, output_dir if mode == "auto_tune" else output_dir / "verify")
        item.artifacts["原始输出目录"] = relative_artifact(
            output_dir if mode == "auto_tune" else output_dir / "verify", self.run_dir
        )
        sla_file = (output_dir if mode == "auto_tune" else output_dir / "verify") / "ucm_sla.json"
        if sla_file.exists():
            item.artifacts["归一化结果"] = relative_artifact(sla_file, self.run_dir)
        self._collect_native_artifacts(
            item, output_dir if mode == "auto_tune" else output_dir / "verify"
        )
        point = next(
            (probe for probe in detail.probes if probe.concurrency == target.concurrency),
            detail.best or (detail.probes[0] if detail.probes else None),
        )
        if detail.target_met:
            item.status = Status.PASSED
            if point and point.concurrency == target.concurrency:
                item.summary = (
                    f"{target.concurrency} 并发达标：TTFT.P90 {point.ttft_p90_ms / 1000:.2f}s，"
                    f"TPOT.P90 {point.tpot_p90_ms:.1f}ms"
                )
            else:
                item.summary = f"{target.concurrency} 并发满足 SLA（EvalScope 原生自动调优结果）"
        elif detail.satisfiable:
            item.status = Status.WARNING
            item.summary = (
                f"{target.concurrency} 并发未达标；EvalScope 原生自动调优建议并发 "
                f"{detail.recommended_concurrency}（p90_ttft / p90_tpot 口径）"
            )
        else:
            item.status = Status.FAILED
            gaps = "；".join(detail.gaps) if detail.gaps else "目标并发下无满足 SLA 的数据"
            item.summary = f"SLA 未达标：{gaps}"
        self._emit(item.summary, level="success" if item.status == Status.PASSED else "warning", fraction=1.0)

    # --------------------------------------------------------------- accuracy
    def _accuracy_params(self, key: str, cfg: dict[str, Any], run_index: int) -> AccuracyParams:
        return AccuracyParams(
            key=key,
            label=str(cfg.get("label", key)),
            dataset=str(cfg.get("dataset", key)),
            subset=str(cfg.get("subset", "") or ""),
            limit=int(cfg.get("limit", self.config.get("accuracy.limit", _FALLBACK_LIMIT)) or 0),
            run_index=run_index,
            request_timeout_s=int(self.config.get("accuracy.request_timeout_s", 14400)),
            extra_args=[str(arg) for arg in (self.config.get("accuracy.extra_args", []) or [])],
            dataset_args=dict(cfg.get("dataset_args", {}) or {}),
        )

    def _run_accuracy(self, item: ItemResult, *, scenario: str | None = None) -> None:
        datasets_cfg: dict[str, Any] = self.config.get("accuracy.datasets", {}) or {}
        runs_per_dataset = max(1, int(self.config.get("accuracy.runs", 2)))
        threshold = float(self.config.get("accuracy.stability_threshold", 0.01))
        output_dir = ensure_dir(self.raw_root / "accuracy")
        total_steps = max(1, len(datasets_cfg) * runs_per_dataset)
        step = 0
        detail = AccuracyDetail(
            runs_per_dataset=runs_per_dataset,
            stability_threshold=threshold,
            note="每项执行两遍，偏差用于核验 KVCache 落盘/读取是否引入精度损失。",
        )
        commands: list[dict[str, Any]] = []
        for key, cfg in datasets_cfg.items():
            dataset = AccuracyDataset(
                key=key,
                label=str(cfg.get("label", key)),
                dataset=str(cfg.get("dataset", key)),
                subset=str(cfg.get("subset", "") or ""),
                description=str(cfg.get("description", "")),
            )
            for run_index in range(1, runs_per_dataset + 1):
                self._check_cancel()
                step += 1
                self._emit(
                    f"精度测试 {dataset.label} 第 {run_index}/{runs_per_dataset} 遍",
                    fraction=step / total_steps * 0.95,
                )
                run_dir = ensure_dir(output_dir / key / f"run{run_index}")
                try:
                    run = self.engine.run_accuracy(
                        self._endpoint(),
                        self._accuracy_params(key, cfg, run_index),
                        run_dir,
                        self._log_fn(),
                        self.cancel_event,
                    )
                except CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - 单次数据集失败仍继续其余项
                    run = AccuracyRun(index=run_index, error=str(exc))
                    self._emit(f"{dataset.label} 第 {run_index} 遍失败：{exc}", level="error")
                dataset.runs.append(run)
                command_file = run_dir / "command.txt"
                if command_file.exists():
                    try:
                        commands.append(
                            {
                                "label": dataset.label,
                                "run": run_index,
                                "command": command_file.read_text(encoding="utf-8").strip(),
                            }
                        )
                    except OSError:
                        pass
            dataset.recompute()
            dataset.stable = bool(
                runs_per_dataset >= 2
                and dataset.delta is not None
                and dataset.delta <= threshold
                and all(run.score is not None for run in dataset.runs)
            )
            detail.datasets.append(dataset)
            detail.total_runs += len(dataset.runs)
        detail.all_stable = bool(detail.datasets) and all(dataset.stable for dataset in detail.datasets)
        detail.commands = commands
        missing = [dataset.label for dataset in detail.datasets if any(run.score is None for run in dataset.runs)]
        unstable = [
            dataset.label
            for dataset in detail.datasets
            if not dataset.stable and dataset.delta is not None and dataset.delta > threshold
        ]
        if not detail.datasets:
            item.status = Status.FAILED
            item.summary = "未配置任何精度数据集"
        elif missing:
            item.status = Status.FAILED
            item.summary = f"精度测试未完成：{', '.join(missing)}"
        elif runs_per_dataset < 2:
            item.status = Status.WARNING
            item.summary = "精度测试仅执行一遍，无法判定 KVCache 落盘一致性"
        elif unstable:
            item.status = Status.WARNING
            item.summary = f"两遍结果不稳定：{', '.join(unstable)}（阈值 {threshold * 100:.1f}pp）"
        else:
            max_delta = max((dataset.delta or 0.0) for dataset in detail.datasets)
            item.status = Status.PASSED
            item.summary = (
                f"四项精度完成；KVCache 一致性正常，最大两遍偏差 {max_delta * 100:.2f}pp"
            )
        detail.note = (
            "每项默认执行两遍；偏差越小，说明 KVCache 落盘/读取引入的精度损失越可控。"
        )
        write_json_atomic(output_dir / "accuracy_summary.json", detail.to_dict())
        self._set_detail(item, detail.to_dict())
        item.artifacts["原始输出目录"] = relative_artifact(output_dir, self.run_dir)
        item.artifacts["归一化结果"] = relative_artifact(
            output_dir / "accuracy_summary.json", self.run_dir
        )
        self._collect_native_artifacts(item, output_dir)
        self._emit(item.summary, level="success" if item.status == Status.PASSED else "warning", fraction=1.0)

    # ------------------------------------------------------------------ agent
    def _run_agent(self, item: ItemResult, *, scenario: str | None = None) -> None:
        target = int(self.config.get("agent.context_required", 262144))
        configured = int(self.config.get("agent.context_detected", 0) or 0)
        detected = configured or None
        if detected is None:
            try:
                detected = self.engine.detect_context(self._endpoint())
            except Exception as exc:  # noqa: BLE001
                self._emit(f"自动探测上下文失败：{exc}", level="warning")
        degraded = bool(detected and detected < target)
        if detected is None:
            self._emit(
                "无法从 /v1/models 探测 max_model_len，按目标上下文执行，未触发降级",
                level="warning",
            )
        elif degraded:
            self._emit(
                f"可用上下文 {detected} < 目标 {target}，切换为 EvalScope AgentX smoke 模式",
                level="warning",
            )
        params = AgentParams(
            target_context=target,
            context_detected=detected,
            parallel=int(self.config.get("agent.parallel", 4)),
            duration_s=int(self.config.get("agent.duration_s", 900)),
            degraded=degraded,
            degraded_mode=str(self.config.get("agent.degraded.mode", "smoke")),
            degraded_parallel=int(self.config.get("agent.degraded.parallel", 1)),
            scenario_name=str(self.config.get("agent.scenario_name", "agentx")),
            tokenizer_path=self._tokenizer(),
            extra_args=[str(arg) for arg in (self.config.get("agent.extra_args", []) or [])],
        )
        output_dir = ensure_dir(self.raw_root / "agent")
        self._emit(
            f"Agent 长会话测试（{'降级 smoke' if degraded else '标准 256K'}）…",
            fraction=0.08,
        )
        detail = self.engine.run_agent(self._endpoint(), params, output_dir, self._log_fn(), self.cancel_event)
        threshold = float(self.config.get("agent.success_threshold", 0.95))
        if detail.completion_rate is None:
            item.status = Status.WARNING
            item.summary = "已执行 AgentX 负载，但未能解析服务级成功率"
        elif detail.completion_rate < threshold:
            item.status = Status.FAILED
            item.summary = f"AgentX 服务级成功率 {percent(detail.completion_rate)}，低于阈值 {percent(threshold)}"
        elif degraded:
            item.status = Status.WARNING
            item.summary = (
                f"降级 smoke 执行：可用上下文 {detail.context_label}；"
                f"服务级成功率 {percent(detail.completion_rate)}（不可与 256K 标准结果直接比较）"
            )
        elif detail.submission_valid is False:
            item.status = Status.WARNING
            item.summary = (
                f"AgentX 结果被标记为 submission_valid=false；服务级成功率 "
                f"{percent(detail.completion_rate)}，请核对原始输出"
            )
        else:
            item.status = Status.PASSED
            item.summary = f"AgentX 服务级成功率 {percent(detail.completion_rate)}"
            if detail.avg_steps is not None:
                item.summary += f"，每会话 {detail.avg_steps:.1f} 次请求"
        self._set_detail(item, detail.to_dict())
        self._attach_command(item, output_dir)
        item.artifacts["原始输出目录"] = relative_artifact(output_dir, self.run_dir)
        agent_file = output_dir / "ucm_agent.json"
        if agent_file.exists():
            item.artifacts["归一化结果"] = relative_artifact(agent_file, self.run_dir)
        self._collect_native_artifacts(item, output_dir)
        self._emit(item.summary, level="success" if item.status == Status.PASSED else "warning", fraction=1.0)

    # ------------------------------------------------------------------ output
    def _collect_native_artifacts(self, item: ItemResult, output_dir: Path) -> None:
        """把 EvalScope 自己的报告挂到索引里，客户可直接打开复核。"""
        patterns = [
            ("EvalScope 原生报告", ("**/report.html", "**/*_report.html")),
            ("EvalScope 性能摘要", ("**/performance_summary.txt",)),
            ("EvalScope 结果 JSON", ("**/results.json", "**/agentx_summary.json")),
        ]
        if not output_dir.exists():
            return
        for label, globs in patterns:
            for pattern in globs:
                matches = sorted(output_dir.glob(pattern))
                if matches:
                    item.artifacts[label] = relative_artifact(matches[0], self.run_dir)
                    break

    def _attach_command(self, item: ItemResult, output_dir: Path) -> None:
        command_file = output_dir / "command.txt"
        if command_file.exists():
            try:
                command = command_file.read_text(encoding="utf-8").strip()
            except OSError:
                command = ""
            if command:
                item.detail["command"] = command
                item.artifacts["EvalScope 执行命令"] = relative_artifact(command_file, self.run_dir)

    @staticmethod
    def _set_detail(item: ItemResult, detail: dict[str, Any]) -> None:
        item.detail = detail

    def write_outputs(self) -> None:
        self.report.finalize()
        report_json = self.run_dir / "report.json"
        self.report.save_json(report_json)
        try:
            html = render_report(self.report, report_dir=self.run_dir)
            (self.run_dir / "report.html").write_text(html, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - 报告渲染失败不应中断测试
            self._append_log(f"报告 HTML 渲染失败：{exc}")
            trace = self.run_dir / "logs" / "report.traceback.txt"
            ensure_dir(trace.parent)
            trace.write_text(traceback.format_exc(), encoding="utf-8")
        set_latest_pointer(self.outputs_root, self.run_dir)
        try:
            (self.run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": self.report.run_id,
                        "conclusion": self.report.conclusion,
                        "reasons": self.report.reasons,
                        "items": {
                            key: {
                                "status": value.status.value,
                                "summary": value.summary,
                                "duration_s": value.duration_s,
                            }
                            for key, value in self.report.items.items()
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
