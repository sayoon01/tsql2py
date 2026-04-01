"""
퓨샷(Few-Shot) 예시 모음
MS SQL Stored Procedure → Python 변환 패턴별 예시.

내용은 prompts/few_shot_examples.yaml 에서 로드합니다.
`examples` 리스트 항목: tag, sql, python 키 필수.
template 에서는 --num-examples(최대 항목 수)만큼 앞에서부터 잘라 사용합니다.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_YAML_NAME = "few_shot_examples.yaml"


def _load_examples() -> list[dict]:
    path = Path(__file__).resolve().with_name(_YAML_NAME)
    if not path.is_file():
        raise FileNotFoundError(
            f"퓨샷 YAML not found: {path}\n"
            f"동일 디렉터리에 {_YAML_NAME} 가 있어야 합니다."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    examples = raw.get("examples")
    if examples is None:
        return []
    if not isinstance(examples, list):
        raise ValueError(f"{path.name}: 'examples' must be a list")

    out: list[dict] = []
    for i, ex in enumerate(examples):
        if not isinstance(ex, dict):
            raise ValueError(f"{path.name}: examples[{i}] must be a mapping")
        for key in ("tag", "sql", "python"):
            if key not in ex:
                raise ValueError(
                    f"{path.name}: examples[{i}] missing required key {key!r}"
                )
        out.append(
            {
                "tag": str(ex["tag"]),
                "sql": str(ex["sql"]),
                "python": str(ex["python"]),
            }
        )
    return out


ALL_EXAMPLES: list[dict] = _load_examples()
