import os
import json
import logging
import shutil
import copy
from typing import Any
from ruamel.yaml import YAML

APP_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = ""
SETTINGS_DIR = ""
CONNECTIONS_DIR = ""
OLD_SETTINGS_JSON_FILE = ""
SETTINGS_FILE = ""
LOG_FILE = ""
MODELS_DEV_CACHE_FILE = ""

MAX_RECENT_FILES = 10
RPM_COOLDOWN_SECONDS = 61
PROVIDER_CUSTOM_HEADERS: dict[str, dict[str, str]] = {}

PROVIDER_API_BASES = {
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "lm_studio": "http://localhost:1234/v1",
    "nvidia_nim": "https://integrate.api.nvidia.com/v1/",
    "openai_compatible": "",
}

PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "mistral": "Mistral AI",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek",
    "ollama": "Ollama",
    "lm_studio": "LM Studio",
    "nvidia_nim": "NVIDIA NIM",
    "openai_compatible": "OpenAI-Compatible",
}

CLOUD_PROVIDERS = [
    "openai",
    "mistral",
    "openrouter",
    "deepseek",
    "nvidia_nim",
    "openai_compatible",
]
LOCAL_PROVIDERS = ["ollama", "lm_studio"]

LOG_PREFIX = "L_G_T"

logger = logging.getLogger(f'{LOG_PREFIX}_CORE.settings')

def initialize_app_paths(project_root_path: str):
    global \
        PROJECT_ROOT, \
        SETTINGS_DIR, \
        CONNECTIONS_DIR, \
        OLD_SETTINGS_JSON_FILE, \
        SETTINGS_FILE, \
        LOG_FILE, \
        MODELS_DEV_CACHE_FILE

    PROJECT_ROOT = project_root_path
    SETTINGS_DIR = os.path.join(PROJECT_ROOT, "settings")
    CONNECTIONS_DIR = os.path.join(SETTINGS_DIR, "connections")
    OLD_SETTINGS_JSON_FILE = os.path.join(PROJECT_ROOT, "translator_settings.json")
    SETTINGS_FILE = os.path.join(SETTINGS_DIR, "app_settings.yaml")
    LOG_FILE = os.path.join(PROJECT_ROOT, "translator.log")
    MODELS_DEV_CACHE_FILE = os.path.join(SETTINGS_DIR, "models_dev_cache.json")

def get_default_generation_params():
    return {
        "enable_model_thinking": True,
        "thinking_budget_value": -1,
        "use_content_as_context": True,
        "temperature": 1.0,
        "top_p": 1.0,
        "max_output_tokens": 0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,}

default_settings: dict[str, Any] = {
    "active_connection_name": "Google Gemini",
    "api_keys": [],
    "current_api_key_index": 0,
    "custom_connections": [],
    "active_model_for_connection": {},
    "gemini_generation_params": get_default_generation_params(),
    "gemini_model": "gemini-2.5-flash-lite-preview-06-17",
    "log_to_file": False,
    "log_level": "INFO",
    "recent_files": [],
    "target_languages": [],
    "available_source_languages": ["English"],
    "selected_target_language": "",
    "selected_source_language": "English",
    "manual_rpm_control": False,
    "api_request_delay": 6.0,
    "rpm_limit": 15,
    "rpm_warning_threshold_percent": 60,
    "rpm_monitor_update_interval_ms": 1000,
    "available_gemini_models": [],
    "auto_save_interval_ms": 5000,
    "api_thread_pool_ratio": 0.75,
    "user_language": "en",
    "ux_hide_discover_limits_warning": False,
    "ux_show_wip_on_startup": True,
    "thinking_failure_threshold": 3,
    }

current_settings: dict[str, Any] = default_settings.copy()

def _migrate_settings(loaded_data: dict[str, Any]) -> dict[str, Any]:
    default_gen_params_keys = get_default_generation_params().keys()
    if any(key in loaded_data for key in default_gen_params_keys):
        logger.info("Old settings format detected. Migrating generation parameters...")
        migrated_gemini_params = get_default_generation_params()
        for key in default_gen_params_keys:
            if key in loaded_data:
                migrated_gemini_params[key] = loaded_data[key]
                del loaded_data[key]
        loaded_data["gemini_generation_params"] = migrated_gemini_params
        if "custom_connections" in loaded_data and isinstance(
            loaded_data["custom_connections"], list
        ):
            for conn in loaded_data["custom_connections"]:
                if isinstance(conn, dict) and "generation_params" not in conn:
                    conn["generation_params"] = get_default_generation_params()
                    if "custom_enable_thinking" in loaded_data:
                        conn["generation_params"]["enable_model_thinking"] = (
                            loaded_data["custom_enable_thinking"]
                        )
        for old_key in ["custom_enable_thinking", "custom_reasoning_effort"]:
            if old_key in loaded_data:
                del loaded_data[old_key]
        logger.info("Migration complete.")
    if "api_key" in loaded_data and isinstance(loaded_data["api_key"], str):
        if "api_keys" not in loaded_data:
            loaded_data["api_keys"] = (
                [loaded_data["api_key"]] if loaded_data["api_key"].strip() else []
            )
            logger.info("Migrated old 'api_key' to 'api_keys' list.")
        del loaded_data["api_key"]
    return loaded_data

def _validate_and_clean_settings(settings_data: dict[str, Any]) -> None:
    if not isinstance(settings_data.get("api_keys"), list):
        settings_data["api_keys"] = []
    num_keys = len(settings_data["api_keys"])
    loaded_idx = settings_data.get("current_api_key_index", 0)
    if not (0 <= loaded_idx < num_keys):
        if num_keys > 0:
            logger.warning(
                f"Loaded current_api_key_index {loaded_idx} out of bounds ({num_keys} keys). Resetting to 0."
            )
        settings_data["current_api_key_index"] = 0
    conns = settings_data.get("custom_connections", [])
    if isinstance(conns, list):
        for conn in conns:
            if isinstance(conn, dict) and "generation_params" not in conn:
                conn["generation_params"] = get_default_generation_params()
        settings_data["custom_connections"] = conns
    else:
        settings_data["custom_connections"] = []
    params = settings_data.get("gemini_generation_params", {})
    if isinstance(params, dict):
        default_params = get_default_generation_params()
        default_params.update(params)
        settings_data["gemini_generation_params"] = default_params
    else:
        settings_data["gemini_generation_params"] = get_default_generation_params()
    if not isinstance(settings_data.get("recent_files"), list):
        settings_data["recent_files"] = []
    settings_data["recent_files"] = [
        f for f in settings_data["recent_files"] if isinstance(f, str) and f
    ][:MAX_RECENT_FILES]
    for lang_key, default_list in [
        ("target_languages", []),
        ("available_source_languages", ["English"]),
    ]:
        if not isinstance(settings_data.get(lang_key), list):
            settings_data[lang_key] = default_list
        current_list = settings_data.get(lang_key, [])
        settings_data[lang_key] = [str(lang) for lang in current_list if lang]
        if not settings_data[lang_key] and default_list:
            settings_data[lang_key] = default_list
    if (
        not settings_data.get("selected_source_language")
        or settings_data["selected_source_language"]
        not in settings_data["available_source_languages"]
    ):
        settings_data["selected_source_language"] = settings_data[
            "available_source_languages"
        ][0]
    if "selected_target_language" not in settings_data:
        settings_data["selected_target_language"] = ""
    if not settings_data.get("gemini_model"):
        settings_data["gemini_model"] = default_settings["gemini_model"]
    if not isinstance(settings_data.get("available_gemini_models"), list):
        settings_data["available_gemini_models"] = []
    settings_data["available_gemini_models"] = [
        str(model) for model in settings_data["available_gemini_models"] if model
    ]
    if "active_model_for_connection" not in settings_data or not isinstance(
        settings_data["active_model_for_connection"], dict
    ):
        settings_data["active_model_for_connection"] = {}

def _migrate_old_json_settings(yaml):
    logger.info("Old 'translator_settings.json' found. Starting migration...")
    try:
        with open(OLD_SETTINGS_JSON_FILE, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        migrated_data = _migrate_settings(old_data)
        connections = migrated_data.pop("custom_connections", [])
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        os.makedirs(CONNECTIONS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(migrated_data, f)
        logger.info(f"Migrated main settings to '{SETTINGS_FILE}'")
        for conn in connections:
            conn_id = conn.get("id")
            if not conn_id:
                logger.warning(
                    f"Skipping migration for a connection without an ID: {conn.get('name')}"
                )
                continue
            conn_path = os.path.join(CONNECTIONS_DIR, f"{conn_id}.yaml")
            with open(conn_path, "w", encoding="utf-8") as f:
                yaml.dump(conn, f)
        logger.info(f"Migrated {len(connections)} connections to '{CONNECTIONS_DIR}'")
        backup_path = OLD_SETTINGS_JSON_FILE + ".bak"
        shutil.move(OLD_SETTINGS_JSON_FILE, backup_path)
        logger.info(
            f"Successfully migrated settings. Old file renamed to '{os.path.basename(backup_path)}'."
        )
        return True
    except Exception as e:
        logger.error(f"Migration from old settings file failed: {e}", exc_info=True)
        return False

def load_settings():
    global current_settings
    current_settings = default_settings.copy()
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    if os.path.exists(OLD_SETTINGS_JSON_FILE):
        _migrate_old_json_settings(yaml)
    os.makedirs(CONNECTIONS_DIR, exist_ok=True)
    loaded_app_settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded_app_settings = yaml.load(f) or {}
            logger.info(f"Loaded app settings from {SETTINGS_FILE}")
        except Exception as e:
            logger.error(
                f"Failed to load app settings file, using defaults. Error: {e}",
                exc_info=True,
            )
    for key, value in loaded_app_settings.items():
        current_settings[key] = value
    loaded_connections = []
    try:
        for filename in os.listdir(CONNECTIONS_DIR):
            if filename.endswith((".yaml", ".yml")):
                file_path = os.path.join(CONNECTIONS_DIR, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        conn_data = yaml.load(f)
                        if isinstance(conn_data, dict) and conn_data.get("id"):
                            loaded_connections.append(conn_data)
                        else:
                            logger.warning(
                                f"Skipping invalid connection file: {filename}"
                            )
                except Exception as e:
                    logger.error(f"Failed to load connection file '{filename}': {e}")
        current_settings["custom_connections"] = loaded_connections
        logger.info(f"Loaded {len(loaded_connections)} custom connections.")
    except Exception as e:
        logger.error(f"Failed to scan connections directory: {e}")
    _validate_and_clean_settings(current_settings)

def save_settings():
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    os.makedirs(CONNECTIONS_DIR, exist_ok=True)
    try:
        settings_to_save = copy.deepcopy(current_settings)
        connections = settings_to_save.pop("custom_connections", [])
        num_keys = len(settings_to_save.get("api_keys", []))
        if not (0 <= settings_to_save.get("current_api_key_index", 0) < num_keys):
            settings_to_save["current_api_key_index"] = 0
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(settings_to_save, f)
        current_conn_ids = {conn["id"] for conn in connections if "id" in conn}
        existing_files = {
            f for f in os.listdir(CONNECTIONS_DIR) if f.endswith((".yaml", ".yml"))
        }
        existing_ids = {os.path.splitext(f)[0] for f in existing_files}
        ids_to_delete = existing_ids - current_conn_ids
        for conn_id in ids_to_delete:
            file_path = os.path.join(CONNECTIONS_DIR, f"{conn_id}.yaml")
            try:
                os.remove(file_path)
                logger.debug(f"Removed obsolete connection file: {file_path}")
            except OSError as e:
                logger.error(
                    f"Failed to remove obsolete connection file {file_path}: {e}"
                )
        for conn in connections:
            conn_id = conn.get("id")
            if not conn_id:
                continue
            file_path = os.path.join(CONNECTIONS_DIR, f"{conn_id}.yaml")
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(conn, f)
        logger.info("Settings and connections saved.")
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")