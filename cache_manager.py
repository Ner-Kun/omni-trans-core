import os
import json
import logging
import hashlib
from PySide6.QtCore import QObject, Signal
from .interfaces import AbstractDataHandler
from . import settings

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.cache')

class CacheManager(QObject):
    cache_dirty_state_changed: Signal = Signal(bool)
    data_handler: AbstractDataHandler
    _is_dirty: bool

    def __init__(self, data_handler: AbstractDataHandler) -> None:
        super().__init__()
        self.data_handler = data_handler
        self.cache: dict[str, str] = {}
        self._is_dirty = False

    def _generate_cache_key(self, source_text: str, source_lang: str, target_lang: str) -> str:
        text_hash = hashlib.sha256(source_text.strip().encode('utf-8')).hexdigest()[:16]
        return f"{source_lang}_{target_lang}_{text_hash}"

    def is_dirty(self) -> bool:
        return self._is_dirty

    def set_dirty_flag(self, dirty: bool) -> None:
        if self._is_dirty != dirty:
            self._is_dirty = dirty
            self.cache_dirty_state_changed.emit(dirty)

    def load_cache(self) -> None:
        self.cache = {}
        cache_path = self.data_handler.get_cache_path()
        if not cache_path:
            logger.info("Cache path not available. Using in-memory cache.")
            return
        if os.path.exists(cache_path):
            logger.info(f"Loading cache from: {cache_path}")
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading cache '{cache_path}': {e}. Using empty cache.", exc_info=True)
                self.cache = {}
        else:
            logger.info(f"No cache file at '{cache_path}'. Starting with empty cache.")

    def save_cache(self):
        cache_path = self.data_handler.get_cache_path()
        if not cache_path:
            return
        logger.info(f"Saving cache to: {cache_path}")
        try:
            temp_path = cache_path + ".tmp"
            with open(file=temp_path, mode='w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, cache_path)
        except Exception as e:
            logger.error(f"Cache Save Error to {cache_path}: {e}", exc_info=True)

    def get_from_cache(self, source_text: str, source_lang: str, target_lang: str) -> str | None:
        key = self._generate_cache_key(source_text, source_lang, target_lang)
        return self.cache.get(key)

    def update_cache(self, source_text: str, translated_text: str, source_lang: str, target_lang: str) -> None:
        key = self._generate_cache_key(source_text, source_lang, target_lang)
        current_value: str | None = self.cache.get(key)
        new_value: str | None = translated_text.strip() if translated_text else None
        if current_value == new_value:
            return
        if new_value:
            self.cache[key] = new_value
        elif key in self.cache:
            del self.cache[key]
        self.set_dirty_flag(True)

    def clear_cache(self) -> None:
        self.cache.clear()
        cache_path = self.data_handler.get_cache_path()
        if cache_path and os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                logger.info(f"Cache file deleted: {cache_path}")
            except OSError as e:
                logger.error(f"Failed to delete cache file {cache_path}: {e}")