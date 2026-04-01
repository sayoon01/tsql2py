"""
Ollama 기반 SQL → Python 변환기
로컬 Ollama 서버 사용 (HuggingFace 토큰 불필요).

model_name 은 `ollama list` 의 이름과 동일해야 하며,
보통 config.yaml 에서 주입합니다.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from prompts.template import build_gemma_prompt
from prompts.post_process import post_process_python, validate_syntax


def _parse_ollama_stream_line(line: object) -> dict | None:
    """Ollama /api/generate 스트림 한 줄 → dict. SSE `data:` 접두사 허용."""
    if line is None:
        return None
    if isinstance(line, str):
        s = line.strip()
    elif isinstance(line, (bytes, bytearray)):
        s = bytes(line).decode("utf-8", errors="replace").strip()
    else:
        s = str(line).strip()
    if not s:
        return None
    if s.startswith("data:"):
        s = s[5:].lstrip()
    if s in ("[DONE]", "{DONE}"):
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


class OllamaConverter:
    """Ollama 로컬 서버를 사용해 MS SQL 프로시저를 Python 코드로 변환합니다."""

    def __init__(
        self,
        model_name: str = "gemma3:12b",
        host: str = "http://localhost:11434",
    ):
        self.model_name = model_name
        self.host = host

    # ─────────── 서버 상태 확인 ───────────
    def check_server(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    # ─────────── 모델 언로드 (빈 메서드, main.py 호환용) ───────────
    def unload_model(self) -> None:
        """Ollama는 서버가 자동 관리하므로 별도 언로드 불필요."""
        pass

    # ─────────── 단일 생성 요청 ───────────
    def _generate(self, gen_body: dict) -> tuple[str, int | None, int | None]:
        """Ollama 에 생성 요청을 보내고 (raw_text, prompt_tokens, output_tokens) 반환."""

        # 스트리밍 시도
        response = requests.post(
            f"{self.host}/api/generate",
            json={**gen_body, "stream": True},
            stream=True,
            timeout=900,
        )

        if response.status_code != 200:
            raise RuntimeError(f"Ollama 오류: {response.text}")

        chunks: list[str] = []
        eval_count: int | None = None
        prompt_eval_count: int | None = None

        for line in response.iter_lines(decode_unicode=False):
            data = _parse_ollama_stream_line(line)
            if data is None:
                continue

            if data.get("error"):
                err = data["error"]
                msg = f"Ollama 오류: {err}"
                if "not found" in str(err).lower():
                    msg += (
                        f"\n→ 로컬에 모델 태그가 없습니다. "
                        f"ollama pull {self.model_name!r} 후 "
                        f"ollama list 로 이름 확인. "
                        f"config.yaml 의 model_name 은 Ollama 에 설치된 이름이어야 합니다."
                    )
                raise RuntimeError(msg)

            piece = data.get("response")
            if isinstance(piece, str) and piece:
                chunks.append(piece)
                print(piece, end="", flush=True)

            if data.get("prompt_eval_count") is not None:
                prompt_eval_count = int(data["prompt_eval_count"])
            if data.get("eval_count") is not None:
                eval_count = int(data["eval_count"])

            if data.get("done"):
                break

        print()
        raw_text = "".join(chunks)

        # 스트림 누락 시 비스트림 fallback
        if not raw_text.strip():
            r2 = requests.post(
                f"{self.host}/api/generate",
                json={**gen_body, "stream": False},
                timeout=900,
            )
            if r2.status_code != 200:
                raise RuntimeError(f"Ollama 오류(비스트림): {r2.text}")
            j2 = r2.json()
            if j2.get("error"):
                raise RuntimeError(f"Ollama 오류: {j2['error']}")
            raw_text = j2.get("response", "") or ""
            if raw_text:
                print(raw_text, end="", flush=True)
                print()
            if j2.get("prompt_eval_count") is not None:
                prompt_eval_count = int(j2["prompt_eval_count"])
            if j2.get("eval_count") is not None:
                eval_count = int(j2["eval_count"])

        return raw_text, prompt_eval_count, eval_count

    # ─────────── 변환 실행 ───────────
    def convert(
        self,
        sql_code: str,
        num_examples: int = 3,
        temperature: float = 0.15,
        top_p: float = 0.9,
        max_new_tokens: int = 4096,
        repetition_penalty: float = 1.1,
        max_retries: int = 2,
    ) -> dict:
        """SQL 프로시저를 Python 코드로 변환합니다.

        AST 구문 오류 발생 시 max_retries 횟수만큼 재시도합니다.
        """
        if not self.check_server():
            raise RuntimeError(
                "Ollama 서버가 실행 중이지 않습니다. "
                "'sudo systemctl start ollama' 실행 후 다시 시도하세요."
            )

        base_prompt = build_gemma_prompt(sql_code, num_examples=num_examples)

        gen_body = {
            "model": self.model_name,
            "prompt": base_prompt,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_new_tokens,
            },
        }

        raw_text = ""
        prompt_eval_count: int | None = None
        eval_count: int | None = None
        python_code = ""
        elapsed = 0.0
        syntax_err: str | None = None

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                print(
                    f"\n🔄 재시도 {attempt}/{max_retries} "
                    f"(구문 오류로 인한 재생성, temperature 소폭 상향)...\n"
                )
                feedback = ""
                if syntax_err:
                    feedback = (
                        f"\n\n[이전 생성 오류]\n{syntax_err}\n"
                        "다음 규칙을 반드시 지키세요:\n"
                        "- 기본값(=None 등)이 있는 파라미터는 기본값 없는 파라미터 뒤에 위치\n"
                        "- 예: def func(conn_str: str, pid: int, name: str | None = None)\n"
                        "- Python 문법 오류 없이 완전한 실행 가능 코드만 출력\n"
                    )
                gen_body["prompt"] = base_prompt + feedback
                # 재시도 시 temperature 살짝 올려 다른 출력 유도
                gen_body["options"]["temperature"] = min(
                    temperature + 0.05 * (attempt - 1), 0.5
                )

            t0 = time.perf_counter()
            raw_text, prompt_eval_count, eval_count = self._generate(gen_body)
            elapsed = time.perf_counter() - t0

            python_code = self._extract_code(raw_text)
            python_code = post_process_python(python_code)

            valid, syntax_err = validate_syntax(python_code)
            if valid:
                break

            print(f"⚠️  구문 오류: {syntax_err}")
            if attempt == max_retries:
                print(
                    f"⚠️  최대 재시도 횟수({max_retries}) 초과. "
                    f"구문 오류가 있는 코드를 반환합니다."
                )

        wordish = len(raw_text.split()) if raw_text.strip() else 0
        out_tok = eval_count if eval_count is not None else wordish

        return {
            "python_code": python_code,
            "raw_output": raw_text,
            "elapsed_sec": round(elapsed, 2),
            "input_tokens": prompt_eval_count or 0,
            "output_tokens": out_tok,
            "model": self.model_name,
            "backend": "ollama",
            "few_shot": num_examples,
        }

    # ─────────── 코드 추출 ───────────
    @staticmethod
    def _extract_code(text: str) -> str:
        """모델 출력에서 Python 코드 블록을 추출합니다."""

        # ```python ... ``` 블록
        match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # ``` ... ``` 블록 (언어 미지정)
        match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 코드 블록 없으면 import/def/class 시작 줄부터 추출
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
                # Gemma turn 태그 제거
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

        safe_name = self.model_name.replace(":", "_").replace("/", "_")
        out_file = output_dir / f"{sql_path.stem}_{safe_name}.py"
        out_file.write_text(result["python_code"], encoding="utf-8")
        result["output_file"] = str(out_file)

        print(
            f"[Ollama:{self.model_name}] 변환 완료: "
            f"{sql_path.name} → {out_file.name} "
            f"({result['elapsed_sec']}초, "
            f"입력 토큰: {result['input_tokens']}, "
            f"출력 토큰: {result['output_tokens']}, "
            f"퓨샷: {result['few_shot']}개)"
        )
        return result
