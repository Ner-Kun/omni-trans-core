from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget
from typing import TypedDict, NotRequired, Any
from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from PySide6 import QtCore
    from .translation_manager import TranslationManager

class JobSignals(QObject):
    job_completed = Signal(dict, str, str, dict, float)
    job_failed = Signal(object, str, str, str, object, dict)
    inspector_update = Signal(str, str, str, str, dict)
    thinking_mode_discovered = Signal(str, str, str)

class TranslatableItem(TypedDict):
    id: str
    source_text: str
    context: str | None
    original_data: dict[str, Any]
    existing_translation: NotRequired[str | None]

class AbstractDataHandler(QObject):
    data_loaded = Signal()
    cache_updated = Signal()
    dirty_state_changed = Signal(bool)

    @abstractmethod
    def is_dirty(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_dirty_flag(self, dirty: bool):
        raise NotImplementedError

    @abstractmethod
    def load(self, path: str):
        raise NotImplementedError

    @abstractmethod
    def save(self):
        raise NotImplementedError
    
    @abstractmethod
    def get_translatable_items(self) -> list[TranslatableItem]:
        raise NotImplementedError

    @abstractmethod
    def update_with_translation(self, item_id: str, translated_text: str):
        raise NotImplementedError

    @abstractmethod
    def get_project_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_cache_path(self) -> str:
        raise NotImplementedError
    
    @abstractmethod
    def get_project_path(self) -> str | None:
        raise NotImplementedError
    
    @abstractmethod
    def get_file_filter(self) -> str:
        raise NotImplementedError

class AbstractTab(QWidget):
    TAB_NAME = "Abstract Tab"
    translation_requested = Signal(list, bool)

    def update_item_display(self, update_data: dict):
        pass

    def on_data_loaded(self):
        pass

    def on_settings_changed(self):
        pass

    def on_before_save(self):
        pass

    def clear_view(self):
        pass

    @abstractmethod
    def update_entry(self, entry_id: str, new_data: dict):
        raise NotImplementedError

    def get_selected_items_for_translation(self) -> list[TranslatableItem]:
        return []

    def flash_items(self, item_ids: list[str]):
        pass

class AbstractConnectionStrategy(ABC):
    @abstractmethod
    def __init__(
        self, manager: "TranslationManager", connection_name: str, settings: dict
    ):
        raise NotImplementedError

    @abstractmethod
    def create_runnable(self, job_data: dict) -> "QtCore.QRunnable":
        raise NotImplementedError

    @abstractmethod
    def get_status_lines(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def on_job_failed(self, job_data: dict, error: Exception, extra_details: dict):
        raise NotImplementedError

    @abstractmethod
    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        raise NotImplementedError

    @abstractmethod
    def dispatch(self) -> None:
        raise NotImplementedError

class AbstractPromptFormatter(ABC):
    @abstractmethod
    def format_prompt(
        self,
        item: TranslatableItem,
        src_lang: str,
        tgt_lang: str,
        custom_settings: dict,
        is_regeneration: bool = False,
    ) -> list[dict]:
        raise NotImplementedError

class UsageMetadata(TypedDict, total=False):
    prompt: int
    thoughts: int
    candidates: int
    total: int

class AbstractResponseParser(ABC):
    @abstractmethod
    def parse(self, response: Any, job_data: dict) -> tuple[str, str, UsageMetadata]:
        raise NotImplementedError
    
class IControlWidgetActions:
    @abstractmethod
    def get_selected_items(self) -> list[TranslatableItem]:
        raise NotImplementedError

    @abstractmethod
    def get_all_items(self) -> list[TranslatableItem]:
        raise NotImplementedError

    @abstractmethod
    def handle_translation_request(
        self, items: list[TranslatableItem], force_regen: bool
    ):
        raise NotImplementedError

    @abstractmethod
    def handle_deletion_request(self, items: list[TranslatableItem]):
        raise NotImplementedError

    @abstractmethod
    def show_info_message(self, title: str, text: str):
        raise NotImplementedError