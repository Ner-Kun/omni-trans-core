import logging
import io
import re
import os
import ast
import json
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme
from rich.highlighter import ReprHighlighter
from rich.text import Text
from typing import override, cast
from collections.abc import Sequence
from . import settings, utils

custom_theme = Theme({
    "log.time": "#29e97c",
    "logging.level.debug": "#11d9e7",
    "logging.level.info": "#0505f3",
    "logging.level.warning": "bold #FF00FF",
    "logging.level.error": "bold #FF0000",
    "logging.level.critical": "bold #FA8072"})

class CombinedHighlighter(ReprHighlighter):
    _patterns: list[tuple[re.Pattern[str], str]]
    def __init__(self) -> None:
        super().__init__()
        self._patterns = [
            (re.compile(r"(?i)\b(API)\b"), "bold #ff2075"),
            (re.compile(r"(?i)\b(Job|dispatch)\b"), "bold #00ff88"),
            (re.compile(r"(?i)\b(cache)\b"), "italic #e786ff"),
            (re.compile(r"(?i)\b(success|completed)\b"), "bold #00af00"),
            (re.compile(r"(?i)\b(failed|error)\b"), "bold #ff0000"),
            (re.compile(r"(?i)\b(warning)\b"), "bold #ffaf00"),
            (re.compile(r"(?i)\b(key|model)\b"), "#d78700"),
            (re.compile(r"(?i)\b(RPM|cooldown)\b"), "#ecc1c1"),]

    @override
    def highlight(self, text: "Text") -> None:
        super().highlight(text)
        for pat, style in self._patterns:
            _ = text.highlight_regex(re_highlight=pat.pattern, style=style)

class ConfigurableLogFilter(logging.Filter):
    inject_name: bool
    keywords_to_suppress: Sequence[str]
    suppress_in_logger: str | None

    def __init__(
        self,
        inject_name: bool = False,
        keywords_to_suppress: Sequence[str] | None = None,
        suppress_in_logger: str | None = None,
    ) -> None:
        super().__init__()
        self.inject_name = inject_name
        self.keywords_to_suppress = keywords_to_suppress or []
        self.suppress_in_logger = (
            suppress_in_logger.lower() if suppress_in_logger else None
        )

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        original_message = record.getMessage()
        record_name_lower = record.name.lower()
        if record_name_lower.startswith("litellm"):
            api_key_pattern = re.compile(
                r"(api_key(?:=|='|=')\s*['\"])([^'\" ]+)(['\"])"
            )
            original_message = api_key_pattern.sub(
                lambda m: f"{m.group(1)}{utils.mask_api_key(m.group(2))}{m.group(3)}",
                original_message,
            )
            record.msg = original_message
            record.args = ()
        if self.keywords_to_suppress and self.suppress_in_logger:
            if record_name_lower.startswith(self.suppress_in_logger):
                for keyword in self.keywords_to_suppress:
                    if keyword in original_message:
                        return False
        try:
            start_char_index = -1
            first_brace = original_message.find("{")
            first_bracket = original_message.find("[")
            if first_brace != -1 and (
                first_bracket == -1 or first_brace < first_bracket
            ):
                start_char_index = first_brace
            elif first_bracket != -1:
                start_char_index = first_bracket
            if start_char_index != -1:
                potential_object_str = original_message[start_char_index:]
                prefix = original_message[:start_char_index]
                data: object = None
                try:
                    data = cast(object, json.loads(potential_object_str))
                except (json.JSONDecodeError, TypeError):
                    try:
                        data = cast(object, ast.literal_eval(potential_object_str))
                    except (ValueError, SyntaxError, TypeError):
                        pass
                if data is not None:
                    try:
                        pretty_data = json.dumps(data, indent=2, ensure_ascii=False)
                        record.msg = prefix + pretty_data
                        record.args = ()
                    except TypeError:
                        pass
        except Exception:
            pass
        if self.inject_name:
            current_msg_str = str(record.msg)
            if not current_msg_str.startswith(f"[{record.name}]"):
                record.msg = f"[{record.name}] {current_msg_str}"
        return True

class LoggerManager:
    settings: dict[str, object]
    recording_console: Console | None

    def __init__(self, settings: dict[str, object]) -> None:
        self.settings = settings
        self.recording_console = None

    def configure_logging(self) -> None:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.DEBUG)
        root = logging.getLogger()
        if root.hasHandlers():
            for handler in root.handlers[:]:
                if hasattr(handler, "close"):
                    handler.close()
                root.removeHandler(handler)
        for name in logging.root.manager.loggerDict:
            logger_instance = logging.getLogger(name)
            if logger_instance.hasHandlers():
                for handler in logger_instance.handlers[:]:
                    if hasattr(handler, "close"):
                        handler.close()
                    logger_instance.removeHandler(handler)
            logger_instance.propagate = True
        root.setLevel(logging.NOTSET)
        filter_config: dict[str, object] = {
            "inject_name": True,
            "suppress_in_logger": "litellm",
            "keywords_to_suppress": [
                "Unable to import proxy_server",
                "This model isn't mapped yet",
                "POST Request Sent from LiteLLM",
                "Request to litellm:",
                "checking potential_model_names",
                "LiteLLM: Params passed to completion()",
                "selected model name for cost calculation",
                "not mapped in model cost map",
                "model_info: {",
                "ModelResponse(id=",
            ],
        }
        log_filter = ConfigurableLogFilter(
            inject_name=cast(bool, filter_config["inject_name"]),
            suppress_in_logger=cast(str, filter_config["suppress_in_logger"]),
            keywords_to_suppress=cast(list[str], filter_config["keywords_to_suppress"]),
        )
        log_level_str = cast(str, self.settings.get("log_level", "INFO"))
        console_handler = RichHandler(
            console=Console(theme=custom_theme, legacy_windows=False),
            rich_tracebacks=True,
            show_path=False,
            highlighter=CombinedHighlighter(),
            log_time_format="[%Y-%m-%d %H:%M:%S.%f]",
            level=getattr(logging, log_level_str.upper(), logging.INFO),
        )
        console_handler.addFilter(log_filter)
        root.addHandler(console_handler)
        log_to_file_enabled = cast(bool, self.settings.get("log_to_file", False))
        if log_to_file_enabled:
            if self.recording_console is None:
                try:
                    self.recording_console = Console(
                        record=True,
                        file=io.StringIO(),
                        theme=custom_theme,
                        width=120,
                        legacy_windows=False,
                    )
                    logging.getLogger(settings.LOG_PREFIX).info(
                        "HTML log recording session started."
                    )
                except Exception as e:
                    print(f"ERROR: Failed to create rich recording console: {e}")
                    self.settings["log_to_file"] = False
                    self.recording_console = None
            if self.recording_console:
                file_log_handler = RichHandler(
                    console=self.recording_console,
                    rich_tracebacks=True,
                    show_path=False,
                    highlighter=CombinedHighlighter(),
                    log_time_format="[%Y-%m-%d %H:%M:%S.%f]",
                )
                file_log_handler.addFilter(log_filter)
                root.addHandler(file_log_handler)
        else:
            self.recording_console = None

    def save_log_to_file(self, log_path: str) -> None:
        if self.recording_console and cast(
            bool, self.settings.get("log_to_file", False)
        ):
            html_log_path = os.path.splitext(log_path)[0] + ".html"
            try:
                logging.getLogger(settings.LOG_PREFIX).info(
                    f"Saving recorded log to HTML file: {html_log_path}"
                )
                self.recording_console.save_html(html_log_path, clear=True)
            except Exception as e:
                print(f"Could not save HTML log: {e}")