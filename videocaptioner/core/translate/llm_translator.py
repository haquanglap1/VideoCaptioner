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
    # 少于这么多条字幕时不构建全局上下文：一份从几行文本里总结出来的"全片简报"
    # 没有参考价值，却要多花一次 LLM 调用（重新翻译选中行就是这种场景）。
    CONTEXT_MIN_SEGMENTS = 10

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
        # 全片原文的确定性指纹，用于缓存键（见 _get_cache_key）
        self.source_signature = ""

    def _prepare(self, translate_data_list: List[SubtitleProcessData]) -> None:
        """翻译前构建一次全局上下文，供所有并行块共享。"""
        # 缓存键需要一个"这是同一个片子"的确定性标识。不能直接用 global_context：
        # 它由 LLM 在 temperature=1 下生成，每次都不一样，会让翻译缓存永远 miss。
        self.source_signature = hashlib.sha256(
            "\n".join(d.original_text for d in translate_data_list).encode("utf-8")
        ).hexdigest()[:16]

        if len(translate_data_list) < self.CONTEXT_MIN_SEGMENTS:
            logger.debug(
                "只有 %d 条字幕，跳过全局上下文构建", len(translate_data_list)
            )
            self.global_context = ""
            return

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

            processed_result = self._extract_translations(result_dict)

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

    def _extract_translations(self, result_dict: Any) -> Dict[str, str]:
        """从 LLM 返回结果中提取译文，跳过结构不合法的条目。

        只接受字符串（反思模式下是嵌套 dict 里的 ``native_translation``）。
        结构不对的条目**不放进结果**，让调用方回退到原文 —— 直接 f-string 化
        会把 ``{'initial_translation': ...}`` 这种 dict 原样写进字幕。
        """
        if not isinstance(result_dict, dict):
            return {}

        processed: Dict[str, str] = {}
        for key, value in result_dict.items():
            text = value
            if isinstance(value, dict):
                text = value.get("native_translation")
            if isinstance(text, (int, float)) and not isinstance(text, bool):
                text = str(text)
            if isinstance(text, str) and text.strip():
                processed[str(key)] = text
            else:
                logger.warning(
                    "字幕 #%s 的译文结构不合法（%s），回退到原文",
                    key,
                    type(value).__name__,
                )
        return processed

    def _agent_loop(
        self, system_prompt: str, subtitle_dict: Dict[str, str]
    ) -> Dict[str, str]:
        """Agent loop翻译字幕块"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(subtitle_dict, ensure_ascii=False)},
        ]
        last_response_dict = None
        last_error = ""
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
                last_error = error_message
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

        # 用完重试次数仍不合法：返回最后一次结果，由 _extract_translations 逐条
        # 过滤，不合法的条目回退到原文。完全不是 dict 就没什么可用的了 —— raise
        # 让整块进入失败统计（BaseTranslator 会保留原文）。
        if not isinstance(last_response_dict, dict):
            raise ValueError(
                f"LLM 返回结构在 {self.MAX_STEPS} 次重试后仍不可用: {last_error}"
            )
        logger.warning(
            "LLM 返回结构在 %d 次重试后仍不完全合法（%s），逐条降级处理",
            self.MAX_STEPS,
            last_error,
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

        除文本/语言/模型外，还纳入反思模式、自定义提示词、全片原文指纹与
        "是否启用了全局上下文"，避免切换这些设置后命中到旧的缓存结果。

        注意用的是 source_signature 而不是 global_context 本身：后者由 LLM
        随机生成，放进键里会让缓存每次都 miss（call_llm 只 memoize 1 小时）。
        """
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        lang = self.target_language.value
        model = self.model
        settings_sig = hashlib.md5(
            f"{self.custom_prompt}\n{self.source_signature}\n"
            f"{bool(self.global_context)}".encode("utf-8")
        ).hexdigest()[:8]
        return (
            f"{class_name}:{chunk_key}:{lang}:{model}"
            f":reflect={int(self.is_reflect)}:{settings_sig}"
        )
