"""모델 출력 Python에 대한 경량 후처리.

역할 (범위):
- 모델이 놓친 **명백한 Python 쪽 버그·비권장 패턴만** 교정 (예: 누락 import, 잘못된
  에러 문자열 관용구, GPT 특유의 실행문 패턴).
- **SQL 로직·구조·의미**는 건드리지 않음. 변환 품질은 프롬프트·퓨샷·모델에 의존.
- 저장 프로시저 입력마다 다른 휴리스틱을 두지 않고, **범용적으로 적용 가능한**
  교정만 둔다.

파이프라인 진입점은 ``post_process_python``.
"""

import re


def fix_misleading_error_messages(code: str) -> str:
    """`Line {e.__class__.__name__}` 처럼 줄번호처럼 보이게 예외 타입만 붙이는 패턴 제거."""
    # f"Line {e.__class__.__name__}: {str(e)}" / {e} 변형
    code = re.sub(
        r'f(["\'])Line\s*\{e\.__class__\.__name__\}\s*:\s*\{str\(e\)\}\1',
        r'f\1{e.__class__.__name__}: {e}\1',
        code,
    )
    code = re.sub(
        r'f(["\'])Line\s*\{e\.__class__\.__name__\}\s*:\s*\{e\}\1',
        r'f\1{e.__class__.__name__}: {e}\1',
        code,
    )
    return code


def post_process_python(code: str) -> str:
    """추출된 Python에 적용하는 후처리 파이프라인."""
    code = fix_missing_imports(code)
    code = fix_gpt_patterns(code)
    code = fix_misleading_error_messages(code)
    return code


def fix_missing_imports(code: str) -> str:
    """생성된 코드에서 누락된 import를 자동으로 추가합니다."""
    # date 타입 쓰는데 import 없으면 추가
    if re.search(r":\s*date\b", code):
        if "from datetime import" in code:
            # datetime은 있는데 date 없으면 추가
            code = re.sub(
                r"from datetime import (datetime)(?!, date)",
                r"from datetime import \1, date",
                code,
            )
        elif "from datetime import" not in code:
            # datetime import 자체가 없으면 통째로 추가
            code = "from datetime import date\n" + code

    return code


def fix_gpt_patterns(code: str) -> str:
    """GPT 출력에서 자주 보이는 비권장 패턴을 보정합니다."""
    # BEGIN TRANSACTION 직접 실행 패턴 -> pyodbc 권장 패턴
    code = code.replace(
        'cursor.execute("BEGIN TRANSACTION")',
        "conn.autocommit = False",
    )
    code = code.replace(
        "cursor.execute('BEGIN TRANSACTION')",
        "conn.autocommit = False",
    )

    # query.format(sort_order=sort_order) 제거 (정렬은 f-string + whitelist 유도)
    code = re.sub(
        r"\.format\(\s*sort_order\s*=\s*sort_order\s*\)",
        "",
        code,
    )

    # SCOPE_IDENTITY() 조회 패턴 -> lastrowid
    code = re.sub(
        r'cursor\.execute\(\s*["\']SELECT\s+SCOPE_IDENTITY\(\)\s*["\']\s*\)\s*\n'
        r'\s*([A-Za-z_]\w*)\s*=\s*cursor\.fetchone\(\)\[0\]',
        r"\1 = cursor.lastrowid",
        code,
    )

    return code
