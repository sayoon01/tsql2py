"""
GPT 기반 SQL → Python 변환기
OpenAI API 사용
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from openai import OpenAI

from prompts.post_process import fix_gpt_patterns, fix_missing_imports
from prompts.template import build_gpt_messages


class GPTConverter:
    """OpenAI GPT 모델을 사용해 MS SQL 프로시저를 Python 코드로 변환합니다."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        api_key: str | None = None,
    ):
        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        )

    # ─────────── 변환 실행 ───────────
    def convert(
        self,
        sql_code: str,
        num_examples: int = 3,
        use_few_shot: bool = True,
        temperature: float = 0.15,
        top_p: float = 0.9,
        max_tokens: int = 4096,
    ) -> dict:
        """
        SQL 프로시저를 Python 코드로 변환합니다.

        Returns:
            dict with keys: python_code, elapsed_sec, input_tokens, output_tokens, cost_usd
        """
        messages = build_gpt_messages(
            sql_code,
            num_examples=num_examples,
            use_few_shot=use_few_shot,
        )

        t0 = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        elapsed = time.perf_counter() - t0

        raw_text = response.choices[0].message.content or ""
        python_code = self._extract_code(raw_text)
        python_code = fix_gpt_patterns(python_code)
        python_code = fix_missing_imports(python_code)

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # 비용 추정 (GPT-4o 기준, 2025년)
        cost = self._estimate_cost(input_tokens, output_tokens)

        return {
            "python_code": python_code,
            "raw_output": raw_text,
            "elapsed_sec": round(elapsed, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "model": self.model_name,
            "backend": "gpt_openai",
            "few_shot": use_few_shot,
        }

    # ─────────── 비용 추정 ───────────
    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """API 호출 비용을 추정합니다."""
        pricing = {
            "gpt-4o":       {"input": 2.50, "output": 10.00},
            "gpt-4o-mini":  {"input": 0.15, "output": 0.60},
            "gpt-4.1":      {"input": 2.00, "output": 8.00},
            "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        }
        rates = pricing.get(self.model_name, {"input": 2.50, "output": 10.00})
        return (
            (input_tokens / 1_000_000) * rates["input"]
            + (output_tokens / 1_000_000) * rates["output"]
        )

    # ─────────── 코드 추출 ───────────
    @staticmethod
    def _extract_code(text: str) -> str:
        """모델 출력에서 Python 코드 블록을 추출합니다."""
        match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 코드 블록 마커 없이 바로 코드가 오는 경우
        lines = text.split("\n")
        code_lines: list[str] = []
        started = False
        for line in lines:
            if not started and (
                line.startswith("import ")
                or line.startswith("from ")
                or line.startswith("def ")
                or line.startswith("class ")
            ):
                started = True
            if started:
                code_lines.append(line)
        return "\n".join(code_lines).strip() if code_lines else text.strip()

    # ─────────── 파일 변환 ───────────
    def convert_file(
        self,
        sql_path: str | Path,
        output_dir: str | Path = "./output",
        **kwargs,
    ) -> dict:
        """SQL 파일을 읽어 변환하고 Python 파일로 저장합니다."""
        sql_path = Path(sql_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        sql_code = sql_path.read_text(encoding="utf-8")
        result = self.convert(sql_code, **kwargs)

        suffix = "gpt_fewshot" if result.get("few_shot", True) else "gpt_zeroshot"
        out_file = output_dir / f"{sql_path.stem}_{suffix}.py"
        out_file.write_text(result["python_code"], encoding="utf-8")
        result["output_file"] = str(out_file)

        print(
            f"[GPT] 변환 완료: {sql_path.name} → {out_file.name} "
            f"({result['elapsed_sec']}초, ${result['cost_usd']:.4f})"
        )
        return result
