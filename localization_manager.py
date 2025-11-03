import os
import json
import logging
import weakref
from PySide6 import QtCore, QtWidgets
from . import settings
from typing import Literal, TypedDict, TypeGuard, cast

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.localization')

class MetadataFile(TypedDict):
    metadata: dict[str, object]

class TranslationFile(TypedDict):
    translations: dict[str, object]

def is_metadata_file(data: object) -> TypeGuard[MetadataFile]:
    return (
        isinstance(data, dict)
        and "metadata" in data
        and isinstance(data["metadata"], dict)
    )


def is_translation_file(data: object) -> TypeGuard[TranslationFile]:
    return (
        isinstance(data, dict)
        and "translations" in data
        and isinstance(data["translations"], dict)
    )

class LocalizationManager(QtCore.QObject):
    language_changed: QtCore.Signal = QtCore.Signal()
    SOURCE_CODE_LANGUAGE: str = "en"

    _source_data: dict[str, str]
    _target_data: dict[str, str]
    _display_mode: Literal["translated", "key", "original"]
    _registered_widgets: "weakref.WeakKeyDictionary[QtCore.QObject, dict[str, tuple[str, dict[str, object]]]]"
    _i18n_core_dir: str | None
    _i18n_app_dir: str | None
    _current_language: str

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._source_data = {}
        self._target_data = {}
        self._display_mode = "translated"
        self._registered_widgets = weakref.WeakKeyDictionary()
        self._translation_dirs: list[str] = []
        core_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n_core")
        if os.path.isdir(core_dir):
            self._translation_dirs.append(core_dir)
        else:
            logger.error(f"Core i18n directory not found at expected path: {core_dir}")
        self._current_language = settings.current_settings.get(
            "user_language", self.SOURCE_CODE_LANGUAGE
        )
        self._load_language_data(self.SOURCE_CODE_LANGUAGE, is_source=True)
        _ = self.language_changed.connect(self._retranslate_all)
        self.set_language(self._current_language)

    def add_translation_directory(self, path: str) -> None:
        if os.path.isdir(path) and path not in self._translation_dirs:
            self._translation_dirs.append(path)
            logger.info(f"Added translation source directory: {path}")

    def get_current_file_paths(self) -> dict[str, str]:
        paths: dict[str, str] = {}
        for i, directory in enumerate(self._translation_dirs):
            scope = "core" if "i18n_core" in directory else f"app_{i}"

            source_path = os.path.join(directory, f"{self.SOURCE_CODE_LANGUAGE}.json")
            if os.path.exists(source_path):
                paths[f"source_{scope}"] = source_path

            if self._current_language != self.SOURCE_CODE_LANGUAGE:
                target_path = os.path.join(directory, f"{self._current_language}.json")
                if os.path.exists(target_path):
                    paths[f"target_{scope}"] = target_path
        return paths

    def get_available_languages(self) -> list[dict[str, str]]:
        languages: dict[str, str] = {}
        paths_to_scan = self._translation_dirs
        for path in paths_to_scan:
            if not (path and os.path.isdir(path)):
                continue
            for filename in os.listdir(path):
                if not filename.endswith(".json"):
                    continue
                lang_code = os.path.splitext(filename)[0]
                if lang_code in languages:
                    continue
                file_path = os.path.join(path, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = cast(dict[str, object], json.load(f))
                    language_name = lang_code.capitalize()
                    if is_metadata_file(data):
                        name = data["metadata"].get("language_name")
                        if isinstance(name, str) and name:
                            language_name = name
                    languages[lang_code] = language_name
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(
                        f"Could not parse {file_path} to get language name: {e}"
                    )
                    languages[lang_code] = lang_code.capitalize()
        return sorted(
            [{"code": code, "name": name} for code, name in languages.items()],
            key=lambda x: x["name"],
        )

    def _load_language_data(self, lang_code: str, is_source: bool) -> None:
        data_dict: dict[str, str] = {}

        def load_file(path_to_json: str) -> dict[str, str]:
            if not os.path.exists(path_to_json):
                logger.debug(f"Localization file not found at {path_to_json}.")
                return {}
            try:
                with open(path_to_json, "r", encoding="utf-8") as f:
                    data = cast(dict[str, object], json.load(f))
                if is_translation_file(data):
                    return {str(k): str(v) for k, v in data["translations"].items()}
                logger.warning(
                    f"File {path_to_json} is missing the 'translations' key or it's not a dictionary."
                )
                return {}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to parse JSON from {path_to_json}: {e}")
                return {}
            except Exception as e:
                logger.error(
                    f"An unexpected error occurred while loading {path_to_json}: {e}"
                )
                return {}

        for directory in self._translation_dirs:
            file_path = os.path.join(directory, f"{lang_code}.json")
            data_dict.update(load_file(file_path))
        if is_source:
            self._source_data = data_dict
            logger.info(
                f"Loaded {len(self._source_data)} source keys for language '{lang_code}'."
            )
        else:
            self._target_data = data_dict
            logger.info(
                f"Loaded {len(self._target_data)} target keys for language '{lang_code}'."
            )

    def set_language(self, lang_code: str) -> None:
        logger.debug(f"Setting language to '{lang_code}'.")
        self._current_language = lang_code
        self._load_language_data(self.SOURCE_CODE_LANGUAGE, is_source=True)
        self._target_data = {}
        if lang_code == self.SOURCE_CODE_LANGUAGE:
            self._target_data = self._source_data.copy()
        else:
            self._load_language_data(lang_code, is_source=False)
        self.language_changed.emit()

    def set_display_mode(self, mode: str) -> None:
        if mode in ["translated", "key", "original"]:
            typed_mode = cast(Literal["translated", "key", "original"], mode)
            if self._display_mode == typed_mode:
                return
            logger.debug(f"Display mode changed to '{typed_mode}'.")
            self._display_mode = typed_mode
            self.language_changed.emit()
        else:
            logger.warning(f"Attempted to set invalid display mode: {mode}")

    def _retranslate_all(self) -> None:
        for widget, properties in list(self._registered_widgets.items()):
            try:
                for internal_prop_name, (key, kwargs) in properties.items():
                    prop_name = internal_prop_name
                    if internal_prop_name.startswith("tabText_"):
                        prop_name = "tabText"
                    self._update_widget_property(widget, prop_name, key, **kwargs)
            except RuntimeError as e:
                if "already deleted" in str(e):
                    logger.debug("Skipping retranslation for a deleted widget.")
                    continue
                else:
                    raise

    def _format_string(self, text: str, **kwargs: object) -> str:
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError) as e:
                logger.warning(
                    f"Formatting text '{text[:30]}...' failed. Missing or invalid placeholder: {e}"
                )
        return text

    def translate(self, key: str, **kwargs: object) -> str:
        if self._display_mode == "key":
            return key
        if self._display_mode == "original":
            source_text: str | None = self._source_data.get(key)
            if source_text is not None:
                return self._format_string(source_text, **kwargs)
            return f"<{key}>"
        target_text: str | None = self._target_data.get(key)
        if target_text is not None:
            return self._format_string(target_text, **kwargs)
        source_text_fallback: str | None = self._source_data.get(key)
        if source_text_fallback is not None:
            return self._format_string(source_text_fallback, **kwargs)
        return f"<{key}>"

    def _update_widget_property(
        self, widget: QtCore.QObject, prop_name: str, key: str, **kwargs: object
    ) -> None:
        text = self.translate(key, **kwargs)
        if prop_name == "tabText":
            index_obj: object | None = kwargs.get("index")
            if isinstance(index_obj, (int, str)) and isinstance(
                widget, QtWidgets.QTabWidget
            ):
                try:
                    widget.setTabText(int(index_obj), text)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid index '{index_obj}' for setTabText on {type(widget).__name__}."
                    )
            else:
                logger.warning(
                    f"Attempted to set tabText for {type(widget).__name__} without a valid index or on wrong widget type."
                )
            return
        setter_name: str = f"set{prop_name[0].upper()}{prop_name[1:]}"
        if hasattr(widget, setter_name):
            getattr(widget, setter_name)(text)
        elif isinstance(widget, QtWidgets.QGroupBox) and prop_name == "title":
            widget.setTitle(text)
        else:
            logger.debug(
                f"Widget {type(widget).__name__} has no property setter '{setter_name}', trying setProperty."
            )
            _ = widget.setProperty(prop_name, text)

    def register(
        self,
        widget: QtCore.QObject,
        prop_name: str,
        key: str,
        format_args: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        final_args: dict[str, object] = format_args.copy() if format_args else {}
        final_args.update(kwargs)
        if widget not in self._registered_widgets:
            self._registered_widgets[widget] = {}
        internal_prop_name = prop_name
        if prop_name == "tabText" and "index" in final_args:
            internal_prop_name = f"{prop_name}_{final_args['index']}"
        self._registered_widgets[widget][internal_prop_name] = (key, final_args)
        self._update_widget_property(widget, prop_name, key, **final_args)

loc_man = LocalizationManager()

def translate(key: str, **kwargs: object) -> str:
    return loc_man.translate(key, **kwargs)