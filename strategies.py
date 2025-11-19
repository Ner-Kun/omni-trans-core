import logging
import time
import collections
import random
import litellm
from typing import Any, Optional
from PySide6 import QtCore
from . import settings, utils
from .interfaces import AbstractConnectionStrategy
from .runnables import GeminiJobRunnable, CustomJobRunnable
from .interfaces import JobSignals
from .localization_manager import translate

try:
    from google import genai
    from google.genai import errors
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    genai: Optional[Any] = None
    errors: Optional[Any] = None
    ResourceExhausted: Optional[Any] = None

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.strategies')

LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT = 75.0
LLM_STRATEGY_DELAY_MAX_DYNAMIC_MS = 4000
LLM_STRATEGY_DELAY_BASE_MS = 1000
LLM_STRATEGY_DELAY_MAX_JITTER_MS = 500

def _cull_and_count_requests(
    timestamps_deque: collections.deque, window_seconds: int
) -> int:
    if not timestamps_deque:
        return 0
    now = time.monotonic()
    cutoff = now - window_seconds
    while timestamps_deque and timestamps_deque[0] < cutoff:
        timestamps_deque.popleft()
    return len(timestamps_deque)

def _cull_and_sum_tokens(token_deque: collections.deque, window_seconds: int) -> int:
    if not token_deque:
        return 0
    now = time.monotonic()
    cutoff = now - window_seconds
    while token_deque and token_deque[0][0] < cutoff:
        token_deque.popleft()
    return sum(item[1] for item in token_deque)

class GeminiStrategy(AbstractConnectionStrategy):
    def __init__(self, manager, connection_name, global_settings):
        self.manager = manager
        self.name = connection_name
        self.settings = global_settings
        self.api_request_timestamps_per_key = {}
        self.api_key_cooldown_end_times = {}
        self.discovered_rpm_limits = {}

    def dispatch(self):
        api_keys = self.settings.get("api_keys", [])
        if not api_keys:
            self.manager.batch_finished.emit("failed (no Gemini API keys)")
            return
        now = time.monotonic()
        key_to_use = None
        sel_key_orig_idx = -1
        num_k = len(api_keys)
        start_idx_rot = self.settings.get("current_api_key_index", 0)
        for i in range(num_k):
            key_idx_chk = (start_idx_rot + i) % num_k
            cand_key = api_keys[key_idx_chk]
            cooldown_end = self.api_key_cooldown_end_times.get(cand_key)
            if cooldown_end and cooldown_end > now:
                continue
            if self._is_rpm_limit_reached_for_key(cand_key):
                self.api_key_cooldown_end_times[cand_key] = (
                    now + settings.RPM_COOLDOWN_SECONDS
                )
                continue
            key_to_use = cand_key
            sel_key_orig_idx = key_idx_chk
            break
        if key_to_use:
            self.settings["current_api_key_index"] = (sel_key_orig_idx + 1) % num_k

            if not self.manager.pending_translation_jobs:
                return

            job_data = self.manager.pending_translation_jobs[0]

            try:
                job_data["api_key"] = key_to_use
                self._record_api_request_timestamp(key_to_use)
                runnable = self.create_runnable(job_data)
                self.manager.thread_pool.start(runnable)
                self.manager.pending_translation_jobs.popleft()
                self.manager.active_translation_jobs += 1

                logger.debug(
                    f"[Gemini] Dispatched job for '{job_data['original_item']['source_text']}'."
                )
            except Exception as e:
                logger.error(f"[Gemini] Failed to dispatch job: {e}", exc_info=True)
                failed_job = self.manager.pending_translation_jobs.popleft()
                self.manager._handle_job_failed(
                    failed_job,
                    str(e),
                    "Dispatch Error",
                    "Failed to start thread/runnable",
                    e,
                )
            if self.manager.pending_translation_jobs:
                self.manager.translation_timer.start(100)
        else:
            wait_times = []
            for k in api_keys:
                cd_end = self.api_key_cooldown_end_times.get(k, 0)
                remaining = cd_end - now

                if remaining > 0:
                    wait_times.append(remaining)

            if wait_times:
                next_attempt_delay_ms = int(min(wait_times) * 1000) + 50
            else:
                next_attempt_delay_ms = 1000

            logger.warning(
                f"All Gemini keys busy/cooldown. Smart waiting: {next_attempt_delay_ms}ms."
            )
            self.manager.translation_timer.start(next_attempt_delay_ms)

    def create_runnable(self, job_data: dict) -> "QtCore.QRunnable":
        signals = JobSignals()
        signals.job_completed.connect(self.manager._handle_job_completed)
        signals.job_failed.connect(self.manager._handle_job_failed)
        signals.inspector_update.connect(self.manager.inspector_update)
        return GeminiJobRunnable(
            job_data,
            signals,
            self.manager.prompt_formatter,
            self.manager.response_parser,
        )

    def get_status_lines(self) -> dict:
        model_name = self.settings.get("gemini_model", "N/A")
        api_keys = self.settings.get("api_keys", [])
        if not api_keys:
            return {
                "message": translate("strategy.gemini.status.no_api_keys"),
                "color": "#FFA500",
            }
        now = time.monotonic()
        rpm_limit = self._get_effective_rpm_limit_for_model(model_name)
        num_keys = len(api_keys)
        if num_keys == 1:
            key = api_keys[0]
            current_rpm = self._get_current_rpm_for_key(key)
            return {
                "model_name": model_name,
                "limits": [{"name": "RPM", "current": current_rpm, "total": rpm_limit}],
            }
        cooldown_keys = []
        available_key_to_dispatch = None
        start_idx = self.settings.get("current_api_key_index", 0)
        for i in range(num_keys):
            key_idx = (start_idx + i) % num_keys
            key = api_keys[key_idx]
            cooldown_end_time = self.api_key_cooldown_end_times.get(key)
            if cooldown_end_time and cooldown_end_time > now:
                cooldown_keys.append({"key": key, "wait": cooldown_end_time - now})
                continue
            current_rpm = self._get_current_rpm_for_key(key)
            if current_rpm >= rpm_limit:
                cooldown_keys.append({"key": key, "wait": 60})
                continue
            if not available_key_to_dispatch:
                available_key_to_dispatch = {"idx": key_idx, "rpm": current_rpm}
        if not available_key_to_dispatch:
            min_wait_time = (
                min(c["wait"] for c in cooldown_keys) if cooldown_keys else 60
            )
            text = translate(
                "strategy.gemini.status.all_keys_cooldown",
                count=num_keys,
                wait_time=f"{min_wait_time:.0f}",
            )
            return {"message": text, "color": "#FF5555"}
        key_at_start_idx = api_keys[start_idx]
        cooldown_end_at_start = self.api_key_cooldown_end_times.get(key_at_start_idx)
        if cooldown_end_at_start and cooldown_end_at_start > now:
            wait_time = cooldown_end_at_start - now
            text = translate(
                "strategy.gemini.status.next_key_cooldown",
                key_text=f"#{start_idx + 1}",
                wait_time=f"{wait_time:.0f}",
            )
            return {"message": text, "color": "#FFA500"}
        idx = available_key_to_dispatch["idx"]
        rpm = available_key_to_dispatch["rpm"]
        return {
            "model_name": f"{model_name} (Key #{idx + 1})",
            "limits": [{"name": "RPM", "current": rpm, "total": rpm_limit}],
        }

    def on_job_failed(self, job_data: dict, error: Exception, extra_details: dict):
        if ResourceExhausted is None or errors is None:
            return
        is_quota_error = isinstance(
            error, (ResourceExhausted, errors.ClientError)
        ) and ("429" in str(error) or "RESOURCE_EXHAUSTED" in str(error).upper())
        if not is_quota_error:
            return
        used_key = job_data.get("api_key", "UNKNOWN_KEY")
        retry_delay = extra_details.get("retry_delay_seconds")
        cooldown = (retry_delay + 3) if retry_delay else settings.RPM_COOLDOWN_SECONDS
        self.api_key_cooldown_end_times[used_key] = time.monotonic() + cooldown
        logger.info(
            f"Cooling down Gemini key {utils.mask_api_key(used_key)} for {cooldown}s."
        )

    def _get_effective_rpm_limit_for_model(self, model_name: str) -> int:
        return self.discovered_rpm_limits.get(
            model_name,
            self.settings.get("rpm_limit", settings.default_settings["rpm_limit"]),
        )

    def _record_api_request_timestamp(self, api_key: str):
        if api_key not in self.api_request_timestamps_per_key:
            self.api_request_timestamps_per_key[api_key] = collections.deque()
        self.api_request_timestamps_per_key[api_key].append(time.monotonic())

    def _get_current_rpm_for_key(self, api_key: str) -> int:
        timestamps = self.api_request_timestamps_per_key.get(api_key)
        return _cull_and_count_requests(timestamps, 60) if timestamps else 0

    def _is_rpm_limit_reached_for_key(self, api_key: str) -> bool:
        model = self.settings.get("gemini_model")
        limit = self._get_effective_rpm_limit_for_model(model)
        return self._get_current_rpm_for_key(api_key) >= limit

    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        pass

    def reset(self):
        pass

class LiteLLMStrategy(AbstractConnectionStrategy):
    def __init__(self, manager, connection_name, connection_settings):
        self.manager = manager
        self.name = connection_name
        self.settings = connection_settings
        self.usage_tracker = {"requests": collections.deque(), "tokens": collections.deque()}
        self.backoff_multiplier = 1.0
        self._pending_job_data: Optional[dict] = None
        self._dispatch_timer = QtCore.QTimer(manager)
        self._dispatch_timer.setSingleShot(True)
        self._dispatch_timer.timeout.connect(self._execute_dispatch)

    def _is_rate_limited(self) -> bool:
        limits = self.settings.get("global_limits", {})
        if (rpd := limits.get("rpd")) is not None and _cull_and_count_requests(
            self.usage_tracker["requests"], 86400
        ) >= rpd:
            return True
        if (rpm := limits.get("rpm")) is not None and _cull_and_count_requests(
            self.usage_tracker["requests"], 60
        ) >= rpm:
            return True
        if (tpm := limits.get("tpm")) is not None and _cull_and_sum_tokens(
            self.usage_tracker["tokens"], 60
        ) >= tpm:
            return True
        return False

    def _execute_dispatch(self):
        job_data = self._pending_job_data
        if not job_data:
            return

        self._pending_job_data = None

        try:
            self.usage_tracker["requests"].append(time.monotonic())
            runnable = self.create_runnable(job_data)
            self.manager.thread_pool.start(runnable)

            self.manager.pending_translation_jobs.popleft()
            self.manager.active_translation_jobs += 1

            logger.debug(
                f"[LiteLLM] Dispatched job for '{job_data['original_item']['source_text']}'."
            )
        except Exception as e:
            logger.error(f"[LiteLLM] Dispatch failed: {e}")
            failed_job = self.manager.pending_translation_jobs.popleft()
            self.manager._handle_job_failed(failed_job, str(e), "Dispatch Error", "", e)

        if self.manager.pending_translation_jobs:
            self.manager.translation_timer.start(100)

    def _calculate_delay_ms(self) -> int:
        limits = self.settings.get("global_limits", {})
        active_model_id = settings.current_settings.get(
            "active_model_for_connection", {}
        ).get(self.name)
        model_config = next(
            (
                m
                for m in self.settings.get("configured_models", [])
                if m.get("model_id") == active_model_id
            ),
            None,
        )
        if model_config and not model_config.get("limits", {}).get(
            "use_global_limits", True
        ):
            limits = model_config.get("limits", {})
        rpm_limit = limits.get("rpm")
        tpm_limit = limits.get("tpm")
        rpm_usage_percent = 0
        if rpm_limit and rpm_limit > 0:
            current_rpm = _cull_and_count_requests(self.usage_tracker["requests"], 60)
            rpm_usage_percent = (current_rpm / rpm_limit) * 100
        tpm_usage_percent = 0
        if tpm_limit and tpm_limit > 0:
            current_tpm = _cull_and_sum_tokens(self.usage_tracker["tokens"], 60)
            tpm_usage_percent = (current_tpm / tpm_limit) * 100
        max_usage_percent = max(rpm_usage_percent, tpm_usage_percent)
        dynamic_delay_ms = 0
        if max_usage_percent > LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT:
            progress_in_warning_zone = (
                max_usage_percent - LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT
            ) / (100.0 - LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT)
            dynamic_delay_ms = LLM_STRATEGY_DELAY_MAX_DYNAMIC_MS * min(
                progress_in_warning_zone, 1.0
            )
        base_delay_ms = LLM_STRATEGY_DELAY_BASE_MS + random.uniform(
            0, LLM_STRATEGY_DELAY_MAX_JITTER_MS
        )
        total_delay = base_delay_ms + dynamic_delay_ms
        logger.debug(
            f"Calculated dispatch delay for '{self.name}': {total_delay:.0f}ms (Usage: {max_usage_percent:.1f}%)"
        )
        return int(total_delay)

    def dispatch(self):
        if self._dispatch_timer.isActive() or self._pending_job_data:
            logger.debug(
                f"Dispatch for '{self.name}' deferred: Another job is already queued on internal timer."
            )
            return
        is_sequential = self.settings.get("wait_for_response", True)
        if is_sequential and self.manager.active_translation_jobs > 0:
            logger.debug(
                f"Dispatch for '{self.name}' deferred: 'Wait for response' is ON."
            )
            return
        if self._is_rate_limited():
            logger.debug(f"Dispatch for '{self.name}' deferred: Rate limit reached.")
            return
        self._pending_job_data = self.manager.pending_translation_jobs[0]
        if is_sequential:
            self._execute_dispatch()
        else:
            delay = self._calculate_delay_ms()
            self._dispatch_timer.start(delay)

    def create_runnable(self, job_data: dict) -> "QtCore.QRunnable":
        signals = JobSignals()
        signals.job_completed.connect(self.manager._handle_job_completed)
        signals.job_failed.connect(self.manager._handle_job_failed)
        signals.inspector_update.connect(self.manager.inspector_update)
        signals.thinking_mode_discovered.connect(
            self.manager._on_thinking_mode_discovered
        )
        return CustomJobRunnable(
            job_data,
            signals,
            self.manager.prompt_formatter,
            self.manager.response_parser,
        )

    def get_status_lines(self) -> dict:
        limits_data = []
        limits = self.settings.get("global_limits", {})
        active_model_id = settings.current_settings.get(
            "active_model_for_connection", {}
        ).get(self.name)
        model_name = "N/A"
        if active_model_id:
            model_name = active_model_id.split("/")[-1]
        model_config = next(
            (
                m
                for m in self.settings.get("configured_models", [])
                if m.get("model_id") == active_model_id
            ),
            None,
        )
        if model_config and not model_config.get("limits", {}).get(
            "use_global_limits", True
        ):
            limits = model_config.get("limits", {})
        if (rpm := limits.get("rpm")) is not None and rpm > 0:
            current = _cull_and_count_requests(self.usage_tracker["requests"], 60)
            limits_data.append({"name": "RPM", "current": current, "total": rpm})
        if (tpm := limits.get("tpm")) is not None and tpm > 0:
            current = _cull_and_sum_tokens(self.usage_tracker["tokens"], 60)
            limits_data.append({"name": "TPM", "current": current, "total": tpm})
        if (rpd := limits.get("rpd")) is not None and rpd > 0:
            current = _cull_and_count_requests(self.usage_tracker["requests"], 86400)
            limits_data.append({"name": "RPD", "current": current, "total": rpd})
        if not limits_data:
            return {"message": translate("strategy.litellm.status.no_limits")}

        return {"model_name": model_name, "limits": limits_data}

    def on_job_failed(self, job_data: dict, error: Exception, extra_details: dict):
        if not litellm or not isinstance(error, litellm.RateLimitError):
            return
        self.backoff_multiplier = min(self.backoff_multiplier + 1.0, 10.0)
        delay = 1000 * self.backoff_multiplier
        logger.warning(
            f"LiteLLM RateLimitError for '{self.name}'. Increasing backoff to {self.backoff_multiplier:.1f}x. Delay: {delay:.0f}ms."
        )
        self.manager.translation_timer.start(int(delay))

    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        self.backoff_multiplier = max(1.0, self.backoff_multiplier / 2.0)
        if usage_metadata:
            token_count = usage_metadata.get("total", 0)
            if token_count > 0:
                self.usage_tracker["tokens"].append((time.monotonic(), token_count))

    def reset(self):
        self._dispatch_timer.stop()
        self._pending_job_data = None