import re


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
