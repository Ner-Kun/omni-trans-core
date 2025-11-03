import logging
from typing import override
from .interfaces import AbstractPromptFormatter, TranslatableItem
from . import settings

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.prompt_formatter')

class DefaultPromptFormatter(AbstractPromptFormatter):
    def __init__(
        self,
        system_prompt: str,
        user_prompt: str,
        regen_prompt: str,
        context_instructions: str = "",
    ):
        self.system_prompt_template: str = system_prompt
        self.user_prompt_template: str = user_prompt
        self.regen_prompt_template: str = regen_prompt
        self.context_instructions_template: str = context_instructions
        logger.debug("DefaultPromptFormatter initialized with custom templates.")

    @override
    def format_prompt(
        self,
        item: TranslatableItem,
        src_lang: str,
        tgt_lang: str,
        custom_settings: dict[str, str],
        is_regeneration: bool = False,
    ) -> list[dict[str, str]]:
        system_template = self.system_prompt_template
        context_template = self.context_instructions_template
        context_content_for_api = None
        use_context = custom_settings.get("use_content_as_context", True)
        if use_context and item.get("context") and str(item["context"]).strip():
            context_content_for_api = str(item["context"]).strip()
        context_instructions_block = ""
        if context_content_for_api and context_template.strip():
            try:
                context_instructions_block = context_template.format(
                    context_section=context_content_for_api
                )
            except KeyError:
                logger.warning(
                    "Context template does not contain {context_section}. Using context directly."
                )
                context_instructions_block = context_content_for_api
        final_system_prompt = system_template.replace(
            "{context_instructions}", context_instructions_block
        )
        try:
            formatted_system_prompt = final_system_prompt.format(
                source_language_name=src_lang, target_language_name=tgt_lang
            )
            if is_regeneration:
                user_template = self.regen_prompt_template
                wrong_keyword = item.get("existing_translation", "")
                formatted_user_prompt = user_template.format(
                    source_language_name=src_lang,
                    target_language_name=tgt_lang,
                    keyword=item["source_text"],
                    wrong_keyword=wrong_keyword,
                )
            else:
                user_template = self.user_prompt_template
                formatted_user_prompt = user_template.format(
                    source_language_name=src_lang,
                    target_language_name=tgt_lang,
                    keyword=item["source_text"],
                )
        except KeyError as e:
            logger.error(f"Missing key in prompt template: {e}")
            formatted_system_prompt = f"Translate from {src_lang} to {tgt_lang}."
            formatted_user_prompt = item["source_text"]
        messages = [
            {"role": "system", "content": formatted_system_prompt},
            {"role": "user", "content": formatted_user_prompt},
        ]
        return messages