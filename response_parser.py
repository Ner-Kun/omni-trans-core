import re
import logging
import importlib.util
from .interfaces import AbstractResponseParser, UsageMetadata
from . import settings
from typing import Any, override


genai_types_available = importlib.util.find_spec("google.genai") is not None
if genai_types_available:
    from google.genai import types as genai_types

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.response_parser')

class DefaultResponseParser(AbstractResponseParser):
    @override
    def parse(
        self, response: Any, job_data: dict[str, Any]
    ) -> tuple[str, str, UsageMetadata]:
        provider = job_data.get("provider")
        if provider == "gemini":
            return self._parse_gemini(response)
        else:
            return self._parse_litellm(response, job_data)

    def _parse_gemini(
        self, response: "genai_types.GenerateContentResponse"
    ) -> tuple[str, str, UsageMetadata]:
        thinking_text_parts = []
        raw_resp_text_parts = []
        usage_metadata: UsageMetadata = {}
        if hasattr(response, "candidates") and response.candidates:
            content = response.candidates[0].content
            if content and content.parts:
                for part in content.parts:
                    part_text = getattr(part, "text", "")
                    if not part_text:
                        continue
                    if hasattr(part, "thought") and part.thought:
                        thinking_text_parts.append(part_text)
                    else:
                        raw_resp_text_parts.append(part_text)
        thinking_text_output = "".join(thinking_text_parts).strip()
        final_processed_translation = "".join(raw_resp_text_parts).strip().strip('"')
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage_metadata["prompt"] = getattr(
                response.usage_metadata, "prompt_token_count", 0
            )
            if hasattr(response.usage_metadata, "thoughts_token_count"):
                usage_metadata["thoughts"] = getattr(
                    response.usage_metadata, "thoughts_token_count", 0
                )
            usage_metadata["candidates"] = getattr(
                response.usage_metadata, "candidates_token_count", 0
            )
            usage_metadata["total"] = getattr(
                response.usage_metadata, "total_token_count", 0
            )
        return final_processed_translation, thinking_text_output, usage_metadata

    def _parse_litellm(
        self, response: Any, job_data: dict[str, Any]
    ) -> tuple[str, str, UsageMetadata]:
        thinking_text = ""
        final_processed_translation = ""
        usage_metadata: UsageMetadata = {}
        try:
            if isinstance(response, dict):
                choices = response.get("choices", [])
                usage = response.get("usage", {})
            elif hasattr(response, "choices"):
                choices = response.choices
                usage = response.usage
            else:
                raise AttributeError("Unsupported response type")
            if not choices:
                raise IndexError("Response has no 'choices'")
            choice = choices[0]
            message = (
                choice.get("message") if isinstance(choice, dict) else choice.message
            )
            raw_content = (
                message.get("content")
                if isinstance(message, dict)
                else getattr(message, "content", "")
            )
            reasoning_content = getattr(message, "reasoning_content", None)
            if reasoning_content:
                thinking_text = str(reasoning_content).strip()
                final_processed_translation = raw_content if raw_content else ""
                logger.debug(
                    "Successfully parsed 'thoughts' using litellm's native 'reasoning_content'."
                )
            elif isinstance(raw_content, list):
                logger.debug("Parsing structured (list) content from response.")
                thinking_parts, translation_parts = [], []
                for part in raw_content:
                    if part.get("type") == "thinking" and "thinking" in part:
                        thinking_content = part["thinking"]
                        if isinstance(thinking_content, list) and thinking_content:
                            thinking_parts.append(thinking_content[0].get("text", ""))
                    elif part.get("type") == "text":
                        translation_parts.append(part.get("text", ""))
                thinking_text = "".join(thinking_parts).strip()
                final_processed_translation = "".join(translation_parts).strip()
            elif isinstance(raw_content, str):
                logger.debug("Parsing standard (string) content from response.")
                parsing_rules = job_data.get("parsing_rules", {})
                start_tag, end_tag = (
                    parsing_rules.get("start_tag"),
                    parsing_rules.get("end_tag"),
                )
                if start_tag and end_tag:
                    pattern = f"{re.escape(start_tag)}(.*?){re.escape(end_tag)}"
                    matches = re.findall(pattern, raw_content, re.DOTALL)
                    if matches:
                        thinking_text = "\n\n---\n\n".join(
                            match.strip() for match in matches
                        )
                        final_processed_translation = re.sub(
                            pattern, "", raw_content, flags=re.DOTALL
                        ).strip()
                    else:
                        final_processed_translation = raw_content
                else:
                    final_processed_translation = raw_content
            final_processed_translation = final_processed_translation.strip().strip('"')
            if (
                not final_processed_translation
                and isinstance(raw_content, str)
                and raw_content
            ):
                final_processed_translation = raw_content.strip().strip('"')
            if usage:
                usage_dict = usage if isinstance(usage, dict) else usage.model_dump()
                usage_metadata["prompt"] = usage_dict.get("prompt_tokens", 0)
                usage_metadata["candidates"] = usage_dict.get("completion_tokens", 0)
                usage_metadata["total"] = usage_dict.get("total_tokens", 0)
        except (AttributeError, IndexError, KeyError) as e:
            logger.error(f"Could not parse LiteLLM response: {e}", exc_info=True)
            return "ERROR: See logs", "", {}
        return final_processed_translation, thinking_text, usage_metadata
