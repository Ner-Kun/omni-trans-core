import logging
import re
import time
import litellm
import os
import json
import urllib.request
import ast
from PySide6 import QtCore
from openai import OpenAI
from . import utils, settings
from .interfaces import AbstractPromptFormatter, AbstractResponseParser, JobSignals
from .localization_manager import translate

try:
    from ruamel.yaml import YAML
except ImportError:
    YAML = None

try:
    from google import genai
    from google.genai import types, errors
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    genai = None
    ResourceExhausted = None
    errors = None
    types = None

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.runnables')

class BaseJobRunnable(QtCore.QRunnable):
    def __init__(
        self,
        job_data: dict,
        signals: JobSignals,
        prompt_formatter: AbstractPromptFormatter,
        response_parser: AbstractResponseParser,
    ):
        super().__init__()
        self.job_data = job_data
        self.signals = signals
        self.prompt_formatter = prompt_formatter
        self.response_parser = response_parser

    def run(self):
        raise NotImplementedError

class GeminiJobRunnable(BaseJobRunnable):
    @QtCore.Slot()
    def run(self):
        if not all([genai, types, errors, ResourceExhausted]):
            err_msg = translate("runnable.gemini.error.library_missing")
            logger.error(err_msg)
            self.signals.job_failed.emit(
                self.job_data, err_msg, "N/A", err_msg, ImportError(err_msg), {}
            )
            return
        job_data = self.job_data
        original_item = job_data["original_item"]
        item_id = original_item["id"]
        text_to_translate_for_log = original_item.get("source_text", "Unknown Text")
        model_name_requested_for_this_job = job_data.get("model_name")
        api_key_for_this_job = job_data.get("api_key")
        generation_params = job_data.get("generation_params", {})
        start_time = time.monotonic()
        try:
            masked_key_log_text = utils.mask_api_key(api_key_for_this_job)
            logger.info(
                f"[Gemini] Job starting for item '{item_id}' with API key: {masked_key_log_text}, Model: {model_name_requested_for_this_job}"
            )
            client = genai.Client(api_key=api_key_for_this_job)
            messages = self.prompt_formatter.format_prompt(
                item=original_item,
                src_lang=job_data["source_lang"],
                tgt_lang=job_data["target_lang"],
                custom_settings=generation_params,
                is_regeneration=job_data.get("is_regeneration", False),
            )
            final_prompt_string = "\n\n".join(
                [msg["content"] for msg in messages if msg.get("role") != "model"]
            )
            if not client:
                raise ValueError("Client object not provided.")
            enable_thinking = generation_params.get("enable_model_thinking", True)
            thinking_budget = generation_params.get("thinking_budget_value", -1)
            thinking_config = None
            if enable_thinking:
                thinking_config = types.ThinkingConfig(
                    include_thoughts=True, thinking_budget=thinking_budget
                )
            elif "flash" in model_name_requested_for_this_job.lower():
                thinking_config = types.ThinkingConfig(thinking_budget=0)
            config_params = {
                "temperature": generation_params.get("temperature", 1.0),
                "top_p": generation_params.get("top_p", 0.95),
                "thinking_config": thinking_config,
                "safety_settings": [
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                ],
            }
            max_tokens = generation_params.get("max_output_tokens", 0)
            if max_tokens > 0:
                config_params["max_output_tokens"] = max_tokens
            final_config_obj = types.GenerateContentConfig(**config_params)
            response = client.models.generate_content(
                model=f"models/{model_name_requested_for_this_job}",
                contents=final_prompt_string,
                config=final_config_obj,
            )
            logger.debug(f"Full Gemini Response: {response!r}")
            duration = time.monotonic() - start_time
            final_processed_translation, thinking_text_output, usage_metadata_output = (
                self.response_parser.parse(response, job_data)
            )
            self.signals.inspector_update.emit(
                model_name_requested_for_this_job,
                final_prompt_string,
                final_processed_translation or "",
                thinking_text_output,
                usage_metadata_output,
            )
            self.signals.job_completed.emit(
                job_data,
                final_processed_translation,
                thinking_text_output,
                usage_metadata_output,
                duration,
            )
        except (ResourceExhausted, errors.ClientError) as e_quota:
            error_message_str = str(e_quota)
            if (
                "429" not in error_message_str
                and "RESOURCE_EXHAUSTED" not in error_message_str.upper()
            ):
                logger.warning(
                    f"Caught {type(e_quota).__name__} but it is not a 429/ResourceExhausted error. Re-raising to generic handler."
                )
                raise e_quota
            masked_key_log_text_err = utils.mask_api_key(api_key_for_this_job)
            logger.error(
                f"Quota Error for '{text_to_translate_for_log}' (Key: {masked_key_log_text_err}): {e_quota}",
                exc_info=False,
            )
            extra_details = {"model_name_from_job": model_name_requested_for_this_job}
            retry_delay_match = re.search(
                r"['\"]retryDelay['\"]\s*:\s*['\"](\d+)s['\"]|retry_delay\s*{\s*seconds:\s*(\d+)\s*}",
                error_message_str,
                re.IGNORECASE,
            )
            if retry_delay_match:
                try:
                    delay_str = retry_delay_match.group(1) or retry_delay_match.group(2)
                    if delay_str:
                        extra_details["retry_delay_seconds"] = int(delay_str)
                except (ValueError, TypeError):
                    pass
            self.signals.job_failed.emit(
                job_data,
                str(e_quota),
                translate("runnable.gemini.error.quota_title"),
                translate("runnable.gemini.error.quota_text", error=str(e_quota)),
                e_quota,
                extra_details,
            )
        except errors.ServerError as e_server:
            masked_key_log_text_err = utils.mask_api_key(api_key_for_this_job)
            logger.error(
                f"[Gemini] Server Error for '{text_to_translate_for_log}' (Key: {masked_key_log_text_err}): {e_server}",
                exc_info=False,
            )
            self.signals.job_failed.emit(
                job_data,
                str(e_server),
                "Gemini API Server Error",
                str(e_server),
                e_server,
                {},
            )
        except Exception as e:
            masked_key_log_text_err_gen = utils.mask_api_key(api_key_for_this_job)
            logger.error(
                f"[Gemini] Exception for '{text_to_translate_for_log}' (Key: {masked_key_log_text_err_gen}): {e}",
                exc_info=True,
            )
            self.signals.job_failed.emit(
                job_data,
                str(e),
                translate("runnable.gemini.error.generic_title"),
                translate("runnable.gemini.error.generic_text", error=str(e)),
                e,
                {},
            )

class CustomJobRunnable(BaseJobRunnable):
    @QtCore.Slot()
    def run(self):
        if not litellm:
            error_msg = translate("runnable.custom.error.library_missing")
            logger.error(f"[LiteLLM] {error_msg}")
            self.signals.job_failed.emit(
                self.job_data, error_msg, "N/A", error_msg, ImportError(error_msg), {}
            )
            return

        job_data = self.job_data
        original_item = job_data["original_item"]
        item_id = original_item["id"]
        generation_params = job_data.get("generation_params", {})
        provider = job_data.get("provider")
        model_name = job_data.get("model_name")
        api_key = job_data.get("api_key")
        base_url = job_data.get("base_url")
        headers = job_data.get("headers")
        thinking_config = job_data.get("thinking_config", {"mode": "unsupported"})

        if not provider or not model_name:
            error_msg = translate("runnable.custom.error.job_misconfigured")
            logger.error(f"[LiteLLM] {error_msg}")
            self.signals.job_failed.emit(
                self.job_data, error_msg, "N/A", error_msg, None, {}
            )
            return

        provider_for_litellm = "openai" if provider == "openai_compatible" else provider
        model_for_litellm = f"{provider_for_litellm}/{model_name}"
        start_time = time.monotonic()
        logger.info(
            f"[LiteLLM] Job starting for item '{item_id}' for '{model_for_litellm}'. Using endpoint: {base_url or 'Default'}"
        )

        try:
            messages = self.prompt_formatter.format_prompt(
                item=original_item,
                src_lang=job_data["source_lang"],
                tgt_lang=job_data["target_lang"],
                custom_settings=generation_params,
                is_regeneration=job_data.get("is_regeneration", False),
            )

            defaults = settings.get_default_generation_params()

            standard_litellm_args = {
                "model": model_for_litellm,
                "messages": messages,
                "api_key": api_key,
                "api_base": base_url,
                "headers": headers,
                "timeout": job_data.get("timeout", 600),
                "temperature": generation_params.get(
                    "temperature", defaults["temperature"]
                ),
                "top_p": generation_params.get("top_p", defaults["top_p"]),
                "max_tokens": generation_params.get(
                    "max_output_tokens", defaults["max_output_tokens"]
                ),
                "frequency_penalty": generation_params.get(
                    "frequency_penalty", defaults["frequency_penalty"]
                ),
                "presence_penalty": generation_params.get(
                    "presence_penalty", defaults["presence_penalty"]
                ),
            }

            custom_provider_params = {}

            if YAML:
                additional_params = job_data.get("additional_params", {})

                include_body_text = additional_params.get(
                    "include_body_params", ""
                ).strip()
                if include_body_text:
                    try:
                        yaml = YAML(typ="safe")
                        parsed_body = yaml.load(include_body_text)
                        if isinstance(parsed_body, dict):
                            custom_provider_params.update(parsed_body)
                            logger.debug(
                                f"[Custom Params] Staged for extra_body: {parsed_body}"
                            )
                        else:
                            logger.warning(
                                "[Custom Params] Parsed include_body_params is not a dictionary, skipping."
                            )
                    except Exception as e:
                        logger.warning(
                            f"[Custom Params] Failed to parse include_body_params YAML/JSON: {e}"
                        )

                exclude_body_text = additional_params.get(
                    "exclude_body_params", ""
                ).strip()
                if exclude_body_text:
                    try:
                        yaml = YAML(typ="safe")
                        parsed_exclude = yaml.load(exclude_body_text)
                        if isinstance(parsed_exclude, list):
                            for key in parsed_exclude:
                                if isinstance(key, str):
                                    standard_litellm_args.pop(key, None)
                            logger.debug(
                                f"[Custom Params] Removed from standard args: {parsed_exclude}"
                            )
                        else:
                            logger.warning(
                                "[Custom Params] Parsed exclude_body_params is not a list, skipping."
                            )
                    except Exception as e:
                        logger.warning(
                            f"[Custom Params] Failed to parse exclude_body_params YAML/JSON: {e}"
                        )

                include_headers_text = additional_params.get(
                    "include_headers", ""
                ).strip()
                if include_headers_text:
                    try:
                        yaml = YAML(typ="safe")
                        parsed_headers = yaml.load(include_headers_text)
                        if isinstance(parsed_headers, dict):
                            if "headers" not in standard_litellm_args or not isinstance(
                                standard_litellm_args["headers"], dict
                            ):
                                standard_litellm_args["headers"] = {}
                            standard_litellm_args["headers"].update(parsed_headers)
                            logger.debug(
                                f"[Custom Params] Added to request headers: {parsed_headers}"
                            )
                        else:
                            logger.warning(
                                "[Custom Params] Parsed include_headers is not a dictionary, skipping."
                            )
                    except Exception as e:
                        logger.warning(
                            f"[Custom Params] Failed to parse include_headers YAML/JSON: {e}"
                        )
            else:
                logger.warning(
                    "ruamel.yaml is not installed. Additional parameters will be ignored."
                )

            should_enable_thinking = generation_params.get(
                "enable_model_thinking", True
            )
            current_mode = thinking_config.get("mode", "unsupported")

            if current_mode == "command":
                cmd = (
                    thinking_config.get("enable_cmd")
                    if should_enable_thinking
                    else thinking_config.get("disable_cmd")
                )
                if cmd:
                    messages[-1]["content"] = f"{cmd}\n{messages[-1]['content']}"
            elif current_mode == "auto" and should_enable_thinking:
                if provider != "mistral":
                    standard_litellm_args["reasoning_effort"] = "auto"

            final_call_args = {
                k: v for k, v in standard_litellm_args.items() if v is not None
            }

            response = None
            try:
                response = litellm.completion(
                    **final_call_args, extra_body=custom_provider_params
                )
            except litellm.APIConnectionError as e:
                error_str = str(e)
                if (
                    "pydantic_core.ValidationError" in error_str
                    and "Input should be a valid string" in error_str
                ):
                    logger.warning(
                        "Caught known litellm parsing error for Mistral-like response. Attempting to recover raw response."
                    )
                    try:
                        match = re.search(
                            r"received_args={'response_object': ({.*?}), 'model_response_object'",
                            error_str,
                            re.DOTALL,
                        )
                        if match:
                            response_object_str = match.group(1)
                            raw_response_dict = ast.literal_eval(response_object_str)
                            logger.info(
                                "Successfully recovered raw response from litellm exception."
                            )
                            response = raw_response_dict
                        else:
                            raise e
                    except (json.JSONDecodeError, ValueError) as parse_error:
                        logger.error(
                            f"Failed to parse recovered response from exception: {parse_error}. Failing job."
                        )
                        raise e
                else:
                    raise e

            duration = time.monotonic() - start_time
            final_processed_translation, thinking_text, usage_meta = (
                self.response_parser.parse(response, job_data)
            )
            prompt_for_inspector = "\n\n".join(
                [f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages]
            )
            self.signals.inspector_update.emit(
                model_name,
                prompt_for_inspector,
                final_processed_translation,
                thinking_text,
                usage_meta,
            )
            self.signals.job_completed.emit(
                job_data,
                final_processed_translation,
                thinking_text,
                usage_meta,
                duration,
            )

        except litellm.RateLimitError as e:
            logger.warning(
                f"[LiteLLM] RateLimitError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.rate_limit_title"),
                translate("runnable.custom.error.rate_limit_text", error=str(e)),
                e,
                {},
            )
        except litellm.Timeout as e:
            logger.warning(
                f"[LiteLLM] Timeout for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.timeout_title"),
                translate("runnable.custom.error.timeout_text", error=str(e)),
                e,
                {},
            )
        except Exception as e:
            logger.error(
                f"[LiteLLM] Unhandled Exception for '{original_item['source_text']}': {e}",
                exc_info=True,
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.generic_title"),
                translate("runnable.custom.error.generic_text", error=str(e)),
                e,
                {},
            )

class FetchModelsWorker(QtCore.QObject):
    finished = QtCore.Signal(list)
    error = QtCore.Signal(str)

    def __init__(self, api_key, base_url):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url

    @QtCore.Slot()
    def run(self):
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            models_response = client.models.list()
            self.finished.emit(models_response.data)
        except Exception as e:
            self.error.emit(str(e))

class ModelInfoWorker(QtCore.QObject):
    finished = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, model_name, provider_id, api_key, api_base):
        super().__init__()
        self.full_model_name = model_name
        self.provider_id = provider_id
        self.api_key = api_key
        self.api_base = api_base

    def _get_models_dev_data(self):
        cache_path = settings.MODELS_DEV_CACHE_FILE
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    logger.debug("Using cached models.dev data.")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(
                    f"Could not read models.dev cache file, will re-fetch. Error: {e}"
                )
        logger.info("Fetching full models.dev registry...")
        try:
            url = "https://models.dev/api.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Omni-Trans-Core"})
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    body = response.read().decode("utf-8")
                    data = json.loads(body)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(body)
                    logger.info("Successfully fetched and cached models.dev registry.")
                    return data
        except Exception as e:
            logger.error(f"Failed to fetch or cache models.dev registry: {e}")
        return None

    def _find_models_in_registry(self, registry, search_term):
        if not registry or not search_term:
            return []
        found_entries = []
        seen_entry_ids = set()
        search_term_lower = search_term.lower()
        for provider_key, provider_data in registry.items():
            if not isinstance(provider_data, dict) or "models" not in provider_data:
                continue
            models_dict = provider_data.get("models", {})
            for model_key, model_info in models_dict.items():
                if not isinstance(model_info, dict):
                    continue
                unique_identifier = (provider_key, model_key)
                if unique_identifier in seen_entry_ids:
                    continue
                model_name = model_info.get("name", "").lower()
                model_id = model_info.get("id", "").lower()
                if (
                    search_term_lower in model_key.lower()
                    or search_term_lower in model_name
                    or search_term_lower in model_id
                ):
                    result_entry = model_info.copy()
                    result_entry["provider_name"] = provider_data.get(
                        "name", provider_key
                    )
                    found_entries.append(result_entry)
                    seen_entry_ids.add(unique_identifier)
        return found_entries

    @QtCore.Slot()
    def run(self):
        try:
            combined_info = {}
            live_data_key = translate("dialog.provider_config.info.live_data_header")
            community_data_key = translate(
                "dialog.provider_config.info.community_data_header"
            )
            static_data_key = translate(
                "dialog.provider_config.info.static_data_header"
            )
            try:
                client = OpenAI(api_key=self.api_key, base_url=self.api_base)
                models_response = client.models.list()
                found_model_obj = next(
                    (m for m in models_response.data if m.id == self.full_model_name),
                    None,
                )
                if found_model_obj:
                    combined_info[live_data_key] = found_model_obj.model_dump()
                else:
                    combined_info[live_data_key] = {
                        "error": translate(
                            "dialog.provider_config.info.error.model_not_found",
                            model_name=self.full_model_name,
                        )
                    }
            except Exception as e:
                combined_info[live_data_key] = {
                    "error": translate(
                        "dialog.provider_config.info.error.could_not_fetch_live_data",
                        error=str(e),
                    )
                }
            models_dev_registry = self._get_models_dev_data()
            if models_dev_registry:
                clean_model_id = self.full_model_name.split("/")[-1].split(":")[0]
                found_entries = self._find_models_in_registry(
                    models_dev_registry, clean_model_id
                )
                if found_entries:
                    combined_info[community_data_key] = found_entries
                else:
                    combined_info[community_data_key] = {
                        "error": translate(
                            "dialog.provider_config.info.error.model_not_found_in_registry",
                            model_name=clean_model_id,
                        )
                    }
            else:
                combined_info[community_data_key] = {
                    "error": translate(
                        "dialog.provider_config.info.error.could_not_load_registry"
                    )
                }
            try:
                full_model_string = f"{self.provider_id}/{self.full_model_name}"
                static_data = litellm.model_cost.get(full_model_string)
                combined_info[static_data_key] = static_data or {
                    "message": translate(
                        "dialog.provider_config.info.message.no_static_data"
                    )
                }
            except Exception as e:
                combined_info[static_data_key] = {
                    "error": translate(
                        "dialog.provider_config.info.error.could_not_fetch_static_data",
                        error=str(e),
                    )
                }
            self.finished.emit(combined_info)
        except Exception as e:
            self.error.emit(str(e))