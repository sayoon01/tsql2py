"""
Gemma 기반 SQL → Python 변환기
HuggingFace Transformers 로컬 GPU 실행
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from prompts.template import build_gemma_prompt


class GemmaConverter:
    """Gemma 모델을 사용해 MS SQL 프로시저를 Python 코드로 변환합니다."""

    def __init__(
        self,
        model_name: str = "google/gemma-3-27b-it",
        load_in_4bit: bool = True,
        load_in_8bit: bool = False,
        device_map: str = "auto",
    ):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self._load_in_4bit = load_in_4bit
        self._load_in_8bit = load_in_8bit
        self._device_map = device_map

    # ─────────── 모델 로드 ───────────
    def load_model(self) -> None:
        """모델과 토크나이저를 GPU에 로드합니다."""
        print(f"[Gemma] 모델 로딩 중: {self.model_name} ...")

        # 양자화 설정
        quantization_config = None
        if self._load_in_4bit:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
        elif self._load_in_8bit:
            quantization_config = BitsAndBytesConfig(load_in_8bit=True)

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            device_map=self._device_map,
            quantization_config=quantization_config,
            torch_dtype=torch.bfloat16,
        )
        print(f"[Gemma] 모델 로드 완료 (디바이스: {self.model.device})")

    # ─────────── 변환 실행 ───────────
    def convert(
        self,
        sql_code: str,
        num_examples: int = 3,
        temperature: float = 0.15,
        top_p: float = 0.9,
        max_new_tokens: int = 4096,
        repetition_penalty: float = 1.1,
    ) -> dict:
        """
        SQL 프로시저를 Python 코드로 변환합니다.

        Returns:
            dict with keys: python_code, elapsed_sec, input_tokens, output_tokens
        """
        if self.model is None:
            self.load_model()

        prompt = build_gemma_prompt(sql_code, num_examples=num_examples)

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        input_len = inputs["input_ids"].shape[1]

        t0 = time.perf_counter()
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                repetition_penalty=repetition_penalty,
            )
        elapsed = time.perf_counter() - t0

        generated_ids = outputs[0][input_len:]
        raw_text = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        python_code = self._extract_code(raw_text)

        return {
            "python_code": python_code,
            "raw_output": raw_text,
            "elapsed_sec": round(elapsed, 2),
            "input_tokens": input_len,
            "output_tokens": len(generated_ids),
            "model": self.model_name,
            "backend": "gemma_hf",
        }

    # ─────────── 코드 추출 ───────────
    @staticmethod
    def _extract_code(text: str) -> str:
        """모델 출력에서 Python 코드 블록을 추출합니다."""
        # ```python ... ``` 블록 추출
        match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # ``` ... ``` 블록 추출
        match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 코드 블록이 없으면 import 또는 def로 시작하는 부분부터 추출
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
                # <end_of_turn> 등 마커에서 중단
                if "<end_of_turn>" in line or "<start_of_turn>" in line:
                    break
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

        out_file = output_dir / f"{sql_path.stem}_gemma.py"
        out_file.write_text(result["python_code"], encoding="utf-8")
        result["output_file"] = str(out_file)

        print(
            f"[Gemma] 변환 완료: {sql_path.name} → {out_file.name} "
            f"({result['elapsed_sec']}초, {result['output_tokens']} 토큰)"
        )
        return result
