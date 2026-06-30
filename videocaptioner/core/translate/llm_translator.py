"""LLM 翻译器（使用 OpenAI）"""

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

import json_repair
import openai

from videocaptioner.core.llm import call_llm
from videocaptioner.core.prompts import get_prompt
from videocaptioner.core.translate.base import BaseTranslator, SubtitleProcessData, logger
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.core.utils.cache import generate_cache_key


class LLMTranslator(BaseTranslator):
    """LLM 翻译器（OpenAI兼容API）"""

    MAX_STEPS = 3
    # 构建全局上下文时发送给模型的原文最大字符数（超出则采样头/中/尾）
    CONTEXT_MAX_CHARS = 12000

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        model: str,
        custom_prompt: str,
        is_reflect: bool,
        update_callback: Optional[Callable],
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )

        self.model = model
        self.custom_prompt = custom_prompt
        self.is_reflect = is_reflect
        # 翻译前由 _prepare 构建的全局上下文简报（主题/语气/术语表）
        self.global_context = ""

    def _prepare(self, translate_data_list: List[SubtitleProcessData]) -> None:
        """翻译前构建一次全局上下文，供所有并行块共享。"""
        self.global_context = self._build_global_context(translate_data_list)

    def _build_global_context(
        self, translate_data_list: List[SubtitleProcessData]
    ) -> str:
        """读取整个字幕原文，生成一份精简的上下文简报（主题/语气/术语表）。

        只调用一次 LLM；失败时返回空字符串以优雅降级（翻译照常进行）。
        """
        if not translate_data_list:
            return ""

        full_text = "\n".join(d.original_text for d in translate_data_list)
        # 超长时采样头/中/尾，避免超出上下文窗口
        if len(full_text) > self.CONTEXT_MAX_CHARS:
            third = self.CONTEXT_MAX_CHARS // 3
            mid_start = (len(full_text) - third) // 2
            full_text = (
                full_text[:third]
                + "\n...\n"
                + full_text[mid_start : mid_start + third]
                + "\n...\n"
                + full_text[-third:]
            )

        prompt = get_prompt("translate/context", target_language=self.target_language)
        try:
            response = call_llm(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": full_text},
                ],
                model=self.model,
            )
            context = response.choices[0].message.content.strip()
            logger.debug(f"[+]已构建全局翻译上下文:\n{context}")
            return context
        except Exception as e:
            logger.warning(f"构建全局上下文失败，跳过（不影响翻译）: {e}")
            return ""

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """翻译字幕块"""
        logger.debug(
            f"[+]正在翻译字幕: {subtitle_chunk[0].index} - {subtitle_chunk[-1].index}"
        )

        # 转换为字典格式用于API调用
        subtitle_dict = {str(data.index): data.original_text for data in subtitle_chunk}

        # 获取提示词
        if self.is_reflect:
            prompt = get_prompt(
                "translate/reflect",
                target_language=self.target_language,
                custom_prompt=self.custom_prompt,
                global_context=self.global_context,
            )
        else:
            prompt = get_prompt(
                "translate/standard",
                target_language=self.target_language,
                custom_prompt=self.custom_prompt,
                global_context=self.global_context,
            )

        try:
            # 使用agent loop进行翻译，自动验证和修正
            result_dict = self._agent_loop(prompt, subtitle_dict)

            # 处理反思翻译模式的结果
            if self.is_reflect and isinstance(result_dict, dict):
                # 记录反思过程（initial/reflection），便于排查为何如此改写，
                # 否则这些已付费生成的字段会被直接丢弃
                for k, v in result_dict.items():
                    if isinstance(v, dict) and v.get("reflection"):
                        logger.debug(
                            f"[reflect #{k}] initial={v.get('initial_translation')!r} "
                            f"reflection={v.get('reflection')!r} "
                            f"-> native={v.get('native_translation')!r}"
                        )
                processed_result = {
                    k: f"{v.get('native_translation', v) if isinstance(v, dict) else v}"
                    for k, v in result_dict.items()
                }
            else:
                processed_result = {k: f"{v}" for k, v in result_dict.items()}

            # 将结果填充回SubtitleProcessData
            for data in subtitle_chunk:
                data.translated_text = processed_result.get(
                    str(data.index), data.original_text
                )
            return subtitle_chunk
        except openai.RateLimitError as e:
            logger.error(f"OpenAI Rate Limit Error: {str(e)}")
            raise
        except openai.AuthenticationError as e:
            logger.error(f"OpenAI Authentication Error: {str(e)}")
            raise
        except openai.NotFoundError as e:
            logger.error(f"OpenAI NotFound Error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"LLM translation error: {e}")
            raise

    def _agent_loop(
        self, system_prompt: str, subtitle_dict: Dict[str, str]
    ) -> Dict[str, str]:
        """Agent loop翻译字幕块"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(subtitle_dict, ensure_ascii=False)},
        ]
        last_response_dict = None
        # llm 反馈循环
        for _ in range(self.MAX_STEPS):
            response = call_llm(messages=messages, model=self.model)
            response_dict = json_repair.loads(
                response.choices[0].message.content.strip()
            )
            last_response_dict = response_dict
            is_valid, error_message = self._validate_llm_response(
                response_dict, subtitle_dict
            )
            if is_valid:
                return response_dict
            else:
                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(response_dict, ensure_ascii=False),
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"Error: {error_message}\n\nFix the errors above and output ONLY a valid JSON dictionary with ALL {len(subtitle_dict)} keys",
                    }
                )

        return last_response_dict

    def _validate_llm_response(
        self, response_dict: Any, subtitle_dict: Dict[str, str]
    ) -> Tuple[bool, str]:
        """验证LLM翻译结果（支持普通和反思模式）

        Returns: (is_valid, error_feedback)
        """
        if not isinstance(response_dict, dict):
            return (
                False,
                f"Output must be a dict, got {type(response_dict).__name__}. Use format: {{'0': 'text', '1': 'text'}}",
            )

        expected_keys = set(subtitle_dict.keys())
        actual_keys = set(response_dict.keys())

        def sort_keys(keys):
            return sorted(keys, key=lambda x: int(x) if x.isdigit() else x)

        # 检查键是否匹配
        if expected_keys != actual_keys:
            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys
            error_parts = []

            if missing:
                error_parts.append(
                    f"Missing keys {sort_keys(missing)} - you must translate these items"
                )
            if extra:
                error_parts.append(
                    f"Extra keys {sort_keys(extra)} - these keys are not in input, remove them"
                )

            return (False, "; ".join(error_parts))

        # 如果是反思模式，检查嵌套结构
        if self.is_reflect:
            for key, value in response_dict.items():
                if not isinstance(value, dict):
                    return (
                        False,
                        f"Key '{key}': value must be a dict with 'native_translation' field. Got {type(value).__name__}.",
                    )

                if "native_translation" not in value:
                    available_keys = list(value.keys())
                    return (
                        False,
                        f"Key '{key}': missing 'native_translation' field. Found keys: {available_keys}. Must include 'native_translation'.",
                    )

        return True, ""

    def _translate_chunk_single(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """单条翻译模式"""
        single_prompt = get_prompt(
            "translate/single", target_language=self.target_language
        )

        for data in subtitle_chunk:
            try:
                response = call_llm(
                    messages=[
                        {"role": "system", "content": single_prompt},
                        {"role": "user", "content": data.original_text},
                    ],
                    model=self.model,
                    temperature=0.7,
                )
                translated_text = response.choices[0].message.content.strip()
                data.translated_text = translated_text
            except Exception as e:
                logger.error(f"Single item translation failed {data.index}: {str(e)}")

        return subtitle_chunk

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        """生成缓存键

        除文本/语言/模型外，还纳入反思模式、自定义提示词与全局上下文，
        避免切换这些设置后命中到旧的、用不同设置生成的缓存结果。
        """
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        lang = self.target_language.value
        model = self.model
        settings_sig = hashlib.md5(
            f"{self.custom_prompt}\n{self.global_context}".encode("utf-8")
        ).hexdigest()[:8]
        return (
            f"{class_name}:{chunk_key}:{lang}:{model}"
            f":reflect={int(self.is_reflect)}:{settings_sig}"
        )
