"""
Gemma / Qwen / GLM 변환 결과 비교·점수·JSON·시각화
"""
from __future__ import annotations

import ast
import difflib
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


# ===================== SCORE =====================
@dataclass
class ConversionScore:
    model: str

    syntax_valid: bool = False
    parameterized_query: bool = False
    has_try_except: bool = False
    has_with_connect: bool = False
    commit_present: bool = False
    rollback_present: bool = False
    placeholder_match: bool = True
    dangerous_pattern_found: bool = False
    function_name_preserved: bool = True

    elapsed_sec: float = 0.0
    token_count: int = 0
    line_count: int = 0

    @property
    def execution_score(self) -> int:
        score = 0
        if self.syntax_valid:
            score += 30
        if self.parameterized_query:
            score += 15
        if self.has_try_except:
            score += 10
        if self.has_with_connect:
            score += 10
        if self.commit_present:
            score += 10
        if self.rollback_present:
            score += 10
        if self.placeholder_match:
            score += 10
        if not self.dangerous_pattern_found:
            score += 5
        return score


# ===================== RESULT =====================
@dataclass
class ComparisonResult:
    sql_file: str
    gemma_score: ConversionScore | None = None
    qwen_score: ConversionScore | None = None
    glm_score: ConversionScore | None = None
    diff_lines: list[str] = field(default_factory=list)
    winner: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql_file": self.sql_file,
            "gemma": self._score_to_dict(self.gemma_score),
            "qwen": self._score_to_dict(self.qwen_score),
            "glm": self._score_to_dict(self.glm_score),
            "winner": self.winner,
        }

    @staticmethod
    def _score_to_dict(score: ConversionScore | None) -> dict[str, Any] | None:
        if not score:
            return None
        d = asdict(score)
        d["execution_score"] = score.execution_score
        return d


# ===================== COMPARATOR =====================
class Comparator:
    MODELS = ("gemma", "qwen", "glm")

    def analyze_code(
        self,
        code: str,
        model: str,
        sql_file: str = "",
        elapsed: float = 0.0,
        tokens: int = 0,
    ) -> ConversionScore:
        score = ConversionScore(
            model=model,
            elapsed_sec=elapsed,
            token_count=tokens,
            line_count=len(code.strip().splitlines()),
        )

        tree: ast.AST | None = None
        try:
            tree = ast.parse(code)
            score.syntax_valid = True
        except SyntaxError:
            score.syntax_valid = False

        lower_code = code.lower()

        score.parameterized_query = (
            ("cursor.execute(" in lower_code and "?" in code)
            or ("params=" in lower_code)
        )
        score.commit_present = ".commit(" in lower_code or "conn.commit()" in lower_code
        score.rollback_present = ".rollback(" in lower_code or "conn.rollback()" in lower_code
        score.has_with_connect = "with pyodbc.connect(" in lower_code

        dangerous_patterns = [
            "cursor.rownumber",
            "@@error",
            "select @@error",
            "lastrowid",
        ]
        score.dangerous_pattern_found = any(p in lower_code for p in dangerous_patterns)

        if tree is not None:
            score.has_try_except = any(isinstance(n, ast.Try) for n in ast.walk(tree))
        else:
            score.has_try_except = "try:" in code and "except" in code

        score.placeholder_match = self._check_placeholder_match(code)
        score.function_name_preserved = self._check_function_name(sql_file, code)

        return score

    def _check_placeholder_match(self, code: str) -> bool:
        pattern = re.compile(
            r'cursor\.execute\s*\(\s*(?P<query>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[\s\S]*?"|\'[\s\S]*?\')\s*(?P<args>,[\s\S]*?)?\)',
            re.MULTILINE,
        )

        for match in pattern.finditer(code):
            query = match.group("query")
            args = match.group("args") or ""

            placeholder_count = query.count("?")

            arg_text = args.strip()
            if not arg_text:
                arg_count = 0
            else:
                arg_text = arg_text.lstrip(",").strip()
                arg_count = len([a for a in arg_text.split(",") if a.strip()])

            if placeholder_count != arg_count and placeholder_count > 0:
                return False

        return True

    def _check_function_name(self, sql_file: str, code: str) -> bool:
        if not sql_file:
            return True

        expected = Path(sql_file).stem.strip().lower()

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return True

        funcs = [n.name.lower() for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        if not funcs:
            return True

        return expected in funcs

    def compare(
        self,
        sql_file: str,
        gemma_result: dict[str, Any] | None = None,
        qwen_result: dict[str, Any] | None = None,
        glm_result: dict[str, Any] | None = None,
    ) -> ComparisonResult:
        """변환 결과 dict(OllamaConverter 반환 형식)끼리 비교."""
        r = ComparisonResult(sql_file=sql_file)

        if gemma_result:
            r.gemma_score = self.analyze_code(
                gemma_result["python_code"],
                model=gemma_result.get("model", "gemma"),
                sql_file=sql_file,
                elapsed=gemma_result.get("elapsed_sec", 0),
                tokens=gemma_result.get("output_tokens", 0),
            )
        if qwen_result:
            r.qwen_score = self.analyze_code(
                qwen_result["python_code"],
                model=qwen_result.get("model", "qwen"),
                sql_file=sql_file,
                elapsed=qwen_result.get("elapsed_sec", 0),
                tokens=qwen_result.get("output_tokens", 0),
            )
        if glm_result:
            r.glm_score = self.analyze_code(
                glm_result["python_code"],
                model=glm_result.get("model", "glm"),
                sql_file=sql_file,
                elapsed=glm_result.get("elapsed_sec", 0),
                tokens=glm_result.get("output_tokens", 0),
            )

        if gemma_result and qwen_result:
            r.diff_lines = list(
                difflib.unified_diff(
                    gemma_result["python_code"].splitlines(),
                    qwen_result["python_code"].splitlines(),
                    fromfile="gemma_output.py",
                    tofile="qwen_output.py",
                    lineterm="",
                )
            )

        scores: dict[str, int] = {}
        if r.gemma_score:
            scores["gemma"] = r.gemma_score.execution_score
        if r.qwen_score:
            scores["qwen"] = r.qwen_score.execution_score
        if r.glm_score:
            scores["glm"] = r.glm_score.execution_score
        if scores:
            r.winner = max(scores, key=scores.get)
        return r

    def build_summary(self, results: list[ComparisonResult]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        wins = {m: 0 for m in self.MODELS}

        for r in results:
            if r.winner in wins:
                wins[r.winner] += 1

        for m in self.MODELS:
            scores = [
                getattr(r, f"{m}_score")
                for r in results
                if getattr(r, f"{m}_score")
            ]
            if not scores:
                continue
            summary[m] = {
                "avg_execution_score": round(mean(s.execution_score for s in scores), 2),
                "syntax_pass_rate": round(mean(int(s.syntax_valid) for s in scores) * 100, 1),
                "placeholder_match_rate": round(mean(int(s.placeholder_match) for s in scores) * 100, 1),
                "commit_rate": round(mean(int(s.commit_present) for s in scores) * 100, 1),
                "rollback_rate": round(mean(int(s.rollback_present) for s in scores) * 100, 1),
                "dangerous_pattern_rate": round(mean(int(s.dangerous_pattern_found) for s in scores) * 100, 1),
                "function_name_preserved_rate": round(mean(int(s.function_name_preserved) for s in scores) * 100, 1),
                "avg_time": round(mean(s.elapsed_sec for s in scores), 2),
                "avg_tokens": round(mean(s.token_count for s in scores), 2),
            }

        return {"models": summary, "wins": wins}

    def save_json(self, results: list[ComparisonResult], path: str | Path) -> str:
        data = [r.to_dict() for r in results]
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(path)

    def generate_report(
        self,
        results: list[Any],
        output_path: str | Path,
        with_plots: bool = False,
    ) -> str:
        """main.py compare/batch 호환: dict 리스트 또는 ComparisonResult 리스트."""
        output_path = Path(output_path)
        normalized = self._normalize_results(results)

        winner_counts = {"gemma": 0, "qwen": 0, "glm": 0}
        for r in normalized:
            if r.winner in winner_counts:
                winner_counts[r.winner] += 1

        report = {
            "summary": {
                "total_files": len(normalized),
                "gemma_wins": winner_counts["gemma"],
                "qwen_wins": winner_counts["qwen"],
                "glm_wins": winner_counts["glm"],
            },
            "details": [r.to_dict() for r in normalized],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if with_plots and normalized:
            plot_dir = output_path.parent / "report"
            self.plot_all(normalized, str(plot_dir))

        return str(output_path)

    @staticmethod
    def _normalize_results(results: list[Any]) -> list[ComparisonResult]:
        out: list[ComparisonResult] = []
        comp = Comparator()
        for r in results:
            if isinstance(r, ComparisonResult):
                out.append(r)
            elif isinstance(r, dict) and any(k in r for k in ("gemma", "qwen", "glm")):
                sql_f = str(r.get("file", r.get("sql_file", "")))
                out.append(
                    comp.compare(
                        sql_file=sql_f,
                        gemma_result=r.get("gemma"),
                        qwen_result=r.get("qwen"),
                        glm_result=r.get("glm"),
                    )
                )
        return out

    # ===================== VISUAL =====================
    def plot_all(self, results: list[ComparisonResult], outdir: str = "report") -> None:
        Path(outdir).mkdir(parents=True, exist_ok=True)
        summary = self.build_summary(results)
        if not summary["models"]:
            return
        self._plot_bar(summary, outdir)
        self._plot_metrics(summary, outdir)
        self._plot_scatter(summary, outdir)
        self._plot_table(summary, outdir)

    def _plot_bar(self, summary: dict[str, Any], outdir: str) -> None:
        models = []
        values = []
        for m, d in summary["models"].items():
            models.append(m)
            values.append(d["avg_execution_score"])
        plt.figure()
        plt.bar(models, values)
        plt.title("Execution Score")
        plt.savefig(f"{outdir}/overall.png")
        plt.close()

    def _plot_metrics(self, summary: dict[str, Any], outdir: str) -> None:
        metrics = ["syntax_pass_rate", "placeholder_match_rate", "commit_rate", "rollback_rate"]
        items = list(summary["models"].items())
        if not items:
            return
        x = np.arange(len(metrics))
        width = min(0.8 / max(len(items), 1), 0.25)
        plt.figure()
        for i, (m, d) in enumerate(items):
            vals = [d[k] for k in metrics]
            plt.bar(x + i * width, vals, width, label=m)
        plt.xticks(x + width * (len(items) - 1) / 2, metrics)
        plt.legend()
        plt.title("Metric Comparison")
        plt.savefig(f"{outdir}/metrics.png")
        plt.close()

    def _plot_scatter(self, summary: dict[str, Any], outdir: str) -> None:
        plt.figure()
        for m, d in summary["models"].items():
            plt.scatter(d["avg_time"], d["avg_execution_score"])
            plt.text(d["avg_time"], d["avg_execution_score"], f" {m}")
        plt.xlabel("Time")
        plt.ylabel("Execution Score")
        plt.title("Speed vs Execution Score")
        plt.savefig(f"{outdir}/scatter.png")
        plt.close()

    def _plot_table(self, summary: dict[str, Any], outdir: str) -> None:
        rows = []
        for m, d in summary["models"].items():
            rows.append(
                [
                    m,
                    d["avg_execution_score"],
                    d["avg_time"],
                    d["avg_tokens"],
                    summary["wins"][m],
                ]
            )
        fig, ax = plt.subplots()
        ax.axis("off")
        table = ax.table(
            cellText=rows,
            colLabels=["Model", "ExecScore", "Time", "Tokens", "Wins"],
            loc="center",
        )
        table.scale(1, 2)
        plt.savefig(f"{outdir}/table.png")
        plt.close()


if __name__ == "__main__":
    # main.py batch / compare 가 넘기는 형식과 동일:
    #  - file: SQL 파일명
    #  - gemma / qwen / glm: ollama_converter.convert_file() 반환 dict
    batch_results = [
        {
            "file": "usp_add_authorbook_storebook.sql",
            "gemma": {
                "python_code": "def f(): pass",
                "elapsed_sec": 10,
                "output_tokens": 200,
                "model": "gemma3:12b",
            },
            "qwen": {
                "python_code": "def g(): pass",
                "elapsed_sec": 8,
                "output_tokens": 180,
                "model": "qwen2.5-coder:14b",
            },
            "glm": {
                "python_code": "def h(): pass",
                "elapsed_sec": 20,
                "output_tokens": 500,
                "model": "glm-4.7-flash:Q4_K_M",
            },
        },
    ]

    comp = Comparator()
    normalized = Comparator._normalize_results(batch_results)

    out = Path("report")
    comp.save_json(normalized, out / "result.json")
    comp.plot_all(normalized, str(out))
    comp.generate_report(batch_results, out / "full_report.json", with_plots=False)

    print("완료: report/ (result.json, full_report.json, *.png)")
