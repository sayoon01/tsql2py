"""
Gemma / Qwen / GLM 변환 결과 비교 엔진
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
    syntax_valid: bool = False
    has_type_hints: bool = False
    has_docstring: bool = False
    uses_parameterized_query: bool = False
    has_error_handling: bool = False
    has_context_manager: bool = False
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
    """3개 모델의 변환 비교 결과"""
    sql_file: str
    gemma_score: ConversionScore | None = None
    qwen_score: ConversionScore | None = None
    glm_score: ConversionScore | None = None
    diff_lines: list[str] = field(default_factory=list)
    winner: str = ""

    def to_dict(self) -> dict:
        return {
            "sql_file": self.sql_file,
            "gemma": self._score_to_dict(self.gemma_score),
            "qwen":  self._score_to_dict(self.qwen_score),
            "glm":   self._score_to_dict(self.glm_score),
            "winner": self.winner,
        }

    @staticmethod
    def _score_to_dict(score: ConversionScore | None) -> dict | None:
        if score is None:
            return None
        d = asdict(score)
        d["quality_score"] = score.quality_score
        return d


class Comparator:
    """3개 모델 변환 결과를 분석하고 비교합니다."""

    # ─────────── 코드 분석 ───────────
    @staticmethod
    def analyze_code(
        code: str,
        model: str,
        elapsed: float = 0,
        tokens: int = 0,
        cost: float = 0,
    ) -> ConversionScore:
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
            "-> " in code
            or ": str" in code
            or ": int" in code
            or ": pd.DataFrame" in code
        )

        # docstring 확인
        score.has_docstring = '"""' in code or "'''" in code

        # 파라미터 바인딩 확인
        score.uses_parameterized_query = (
            "params=" in code
            or "params=[" in code
            or ", ?" in code
            or "(?," in code
            or ('", ' in code and "cursor.execute" in code)
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
        qwen_result: dict | None = None,
        glm_result: dict | None = None,
    ) -> ComparisonResult:
        """3개 모델의 변환 결과를 비교합니다."""
        comparison = ComparisonResult(sql_file=sql_file)

        if gemma_result:
            comparison.gemma_score = self.analyze_code(
                gemma_result["python_code"],
                model=gemma_result.get("model", "gemma"),
                elapsed=gemma_result.get("elapsed_sec", 0),
                tokens=gemma_result.get("output_tokens", 0),
            )

        if qwen_result:
            comparison.qwen_score = self.analyze_code(
                qwen_result["python_code"],
                model=qwen_result.get("model", "qwen"),
                elapsed=qwen_result.get("elapsed_sec", 0),
                tokens=qwen_result.get("output_tokens", 0),
            )

        if glm_result:
            comparison.glm_score = self.analyze_code(
                glm_result["python_code"],
                model=glm_result.get("model", "glm"),
                elapsed=glm_result.get("elapsed_sec", 0),
                tokens=glm_result.get("output_tokens", 0),
            )

        # Diff 생성 (Gemma vs Qwen 기준)
        if gemma_result and qwen_result:
            comparison.diff_lines = list(difflib.unified_diff(
                gemma_result["python_code"].splitlines(),
                qwen_result["python_code"].splitlines(),
                fromfile="gemma_output.py",
                tofile="qwen_output.py",
                lineterm="",
            ))

        # 승자 판정
        scores: dict[str, int] = {}
        if comparison.gemma_score:
            scores["gemma"] = comparison.gemma_score.quality_score
        if comparison.qwen_score:
            scores["qwen"] = comparison.qwen_score.quality_score
        if comparison.glm_score:
            scores["glm"] = comparison.glm_score.quality_score

        if scores:
            comparison.winner = max(scores, key=scores.get)

        return comparison

    # ─────────── 리포트 생성 ───────────
    def generate_report(
        self,
        results: list,
        output_path: str | Path,
    ) -> str:
        """비교 결과를 JSON 리포트로 저장합니다."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        details: list[dict] = []
        winner_counts: dict[str, int] = {"gemma": 0, "qwen": 0, "glm": 0}

        for r in results:
            # ComparisonResult 객체
            if isinstance(r, ComparisonResult):
                d = r.to_dict()
                if r.winner in winner_counts:
                    winner_counts[r.winner] += 1
                details.append(d)

            # batch에서 넘어오는 dict
            # {"file": str, "gemma": result_dict, "qwen": result_dict, "glm": result_dict}
            elif isinstance(r, dict) and "gemma" in r:
                entry: dict = {"file": r.get("file", "")}
                quality: dict[str, int] = {}

                for key in ("gemma", "qwen", "glm"):
                    res = r.get(key)
                    if not res:
                        entry[key] = None
                        continue
                    s = self.analyze_code(
                        res["python_code"],
                        model=res.get("model", key),
                        elapsed=res.get("elapsed_sec", 0),
                        tokens=res.get("output_tokens", 0),
                    )
                    d = asdict(s)
                    d["quality_score"] = s.quality_score
                    entry[key] = d
                    quality[key] = s.quality_score

                winner = max(quality, key=quality.get) if quality else ""
                entry["winner"] = winner
                if winner in winner_counts:
                    winner_counts[winner] += 1
                details.append(entry)

        report = {
            "summary": {
                "total_files": len(results),
                "gemma_wins": winner_counts["gemma"],
                "qwen_wins":  winner_counts["qwen"],
                "glm_wins":   winner_counts["glm"],
            },
            "details": details,
        }

        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return str(output_path)