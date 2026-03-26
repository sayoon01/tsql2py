"""
Gemma vs GPT 변환 결과 비교 엔진
"""
from __future__ import annotations

import ast
import difflib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ConversionScore:
    """단일 변환 결과의 품질 점수"""
    model: str
    syntax_valid: bool = False          # Python 구문 오류 없음
    has_type_hints: bool = False        # 타입힌트 사용
    has_docstring: bool = False         # docstring 포함
    uses_parameterized_query: bool = False  # 파라미터 바인딩 사용 (? 플레이스홀더)
    has_error_handling: bool = False    # try/except 포함
    has_context_manager: bool = False   # with 문 사용
    line_count: int = 0
    elapsed_sec: float = 0.0
    token_count: int = 0
    cost_usd: float = 0.0

    @property
    def quality_score(self) -> int:
        """품질 점수 (0~100)"""
        score = 0
        if self.syntax_valid:
            score += 30
        if self.has_type_hints:
            score += 15
        if self.has_docstring:
            score += 10
        if self.uses_parameterized_query:
            score += 20
        if self.has_error_handling:
            score += 15
        if self.has_context_manager:
            score += 10
        return score


@dataclass
class ComparisonResult:
    """두 모델의 변환 비교 결과"""
    sql_file: str
    gemma_score: ConversionScore | None = None
    gpt_score: ConversionScore | None = None
    gpt_zeroshot_score: ConversionScore | None = None
    diff_lines: list[str] = field(default_factory=list)
    winner: str = ""

    def to_dict(self) -> dict:
        return {
            "sql_file": self.sql_file,
            "gemma": asdict(self.gemma_score) if self.gemma_score else None,
            "gpt_fewshot": asdict(self.gpt_score) if self.gpt_score else None,
            "gpt_zeroshot": asdict(self.gpt_zeroshot_score) if self.gpt_zeroshot_score else None,
            "winner": self.winner,
        }


class Comparator:
    """두 변환 결과를 분석하고 비교합니다."""

    # ─────────── 코드 분석 ───────────
    @staticmethod
    def analyze_code(code: str, model: str, elapsed: float = 0, tokens: int = 0, cost: float = 0) -> ConversionScore:
        """Python 코드의 품질을 분석합니다."""
        score = ConversionScore(
            model=model,
            elapsed_sec=elapsed,
            token_count=tokens,
            cost_usd=cost,
            line_count=len(code.strip().splitlines()),
        )

        # 구문 검증
        try:
            ast.parse(code)
            score.syntax_valid = True
        except SyntaxError:
            score.syntax_valid = False

        # 타입힌트 확인
        score.has_type_hints = bool(
            "-> " in code or ": str" in code or ": int" in code or ": pd.DataFrame" in code
        )

        # docstring 확인
        score.has_docstring = '"""' in code or "'''" in code

        # 파라미터 바인딩 확인 (? 플레이스홀더 또는 %s)
        score.uses_parameterized_query = (
            "params=" in code
            or "params=[" in code
            or ", ?" in code
            or "(?," in code
            or '", ' in code and "cursor.execute" in code
        )

        # 에러 처리 확인
        score.has_error_handling = "try:" in code and "except" in code

        # 컨텍스트 매니저 확인
        score.has_context_manager = "with " in code and "conn" in code.lower()

        return score

    # ─────────── 비교 실행 ───────────
    def compare(
        self,
        sql_file: str,
        gemma_result: dict | None = None,
        gpt_result: dict | None = None,
        gpt_zeroshot_result: dict | None = None,
    ) -> ComparisonResult:
        """두 모델의 변환 결과를 비교합니다."""
        comparison = ComparisonResult(sql_file=sql_file)

        if gemma_result:
            comparison.gemma_score = self.analyze_code(
                gemma_result["python_code"],
                model=gemma_result.get("model", "gemma"),
                elapsed=gemma_result.get("elapsed_sec", 0),
                tokens=gemma_result.get("output_tokens", 0),
            )

        if gpt_result:
            comparison.gpt_score = self.analyze_code(
                gpt_result["python_code"],
                model=gpt_result.get("model", "gpt"),
                elapsed=gpt_result.get("elapsed_sec", 0),
                tokens=gpt_result.get("output_tokens", 0),
                cost=gpt_result.get("cost_usd", 0),
            )

        if gpt_zeroshot_result:
            comparison.gpt_zeroshot_score = self.analyze_code(
                gpt_zeroshot_result["python_code"],
                model=gpt_zeroshot_result.get("model", "gpt") + " (zero-shot)",
                elapsed=gpt_zeroshot_result.get("elapsed_sec", 0),
                tokens=gpt_zeroshot_result.get("output_tokens", 0),
                cost=gpt_zeroshot_result.get("cost_usd", 0),
            )

        # Diff 생성
        if gemma_result and gpt_result:
            comparison.diff_lines = list(difflib.unified_diff(
                gemma_result["python_code"].splitlines(),
                gpt_result["python_code"].splitlines(),
                fromfile="gemma_output.py",
                tofile="gpt_output.py",
                lineterm="",
            ))

        # 승자 판정
        scores = {}
        if comparison.gemma_score:
            scores["gemma"] = comparison.gemma_score.quality_score
        if comparison.gpt_score:
            scores["gpt_fewshot"] = comparison.gpt_score.quality_score
        if comparison.gpt_zeroshot_score:
            scores["gpt_zeroshot"] = comparison.gpt_zeroshot_score.quality_score

        if scores:
            comparison.winner = max(scores, key=scores.get)

        return comparison

    # ─────────── 리포트 생성 ───────────
    @staticmethod
    def generate_report(results: list[ComparisonResult], output_path: str | Path) -> str:
        """비교 결과를 JSON 리포트로 저장합니다."""
        output_path = Path(output_path)
        report = {
            "summary": {
                "total_files": len(results),
                "gemma_wins": sum(1 for r in results if r.winner == "gemma"),
                "gpt_fewshot_wins": sum(1 for r in results if r.winner == "gpt_fewshot"),
                "gpt_zeroshot_wins": sum(1 for r in results if r.winner == "gpt_zeroshot"),
            },
            "details": [r.to_dict() for r in results],
        }

        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(output_path)
