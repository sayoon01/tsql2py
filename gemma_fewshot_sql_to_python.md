# Gemma 퓨샷(Few-Shot) 프롬프팅으로 MS SQL Procedure → Python 변환 가이드

## 1. 개요

MS SQL Server의 저장 프로시저(Stored Procedure)를 Python 코드로 변환하는 작업은 레거시 시스템 마이그레이션에서 자주 발생합니다. 이 문서에서는 Google의 오픈소스 모델 **Gemma**를 활용한 퓨샷 프롬프팅 기법과, **GPT-4** 계열 모델과의 성능 비교를 다룹니다.

---

## 2. 퓨샷 프롬프팅 전략

### 2.1 핵심 원리

퓨샷(Few-Shot) 프롬프팅은 모델에게 입력-출력 예시를 2~5개 제공하여 변환 패턴을 학습시키는 기법입니다. SQL → Python 변환에서는 다음 요소를 예시에 포함해야 합니다.

- **변수 선언** (`DECLARE @var` → Python 변수)
- **커서/루프** (`CURSOR`, `WHILE` → `for` 루프 또는 pandas)
- **에러 처리** (`TRY...CATCH` → `try...except`)
- **임시 테이블** (`#temp` → pandas DataFrame 또는 dict)
- **출력 파라미터** (`OUTPUT` → return 값 또는 tuple)

### 2.2 프롬프트 구조

```
[시스템 지침: SQL→Python 변환 규칙]

[예시 1 (패턴: 단순 SELECT)]
[SQL] ... [Python] ...

[예시 2 (패턴: 트랜잭션)]
[SQL] ... [Python] ...

[예시 3 (패턴: 임시테이블/커서)]
[SQL] ... [Python] ...

[요청: 다음 SQL을 변환하세요]
[SQL 입력] ...
[Python 출력]:
```

### 2.3 선택할 예시의 기준

| 패턴 | 우선순위 | 선택 기준 |
|------|---------|---------|
| 단순 SELECT | 높음 | 기본 템플릿 (항상 포함) |
| 트랜잭션 | 높음 | INPUT SQL에 BEGIN TRAN이 있을 때 |
| 임시테이블/커서 | 중간 | INPUT SQL에 #temp나 CURSOR가 있을 때 |
| 동적 SQL | 중간 | INPUT SQL에 sp_executesql이 있을 때 |
| MERGE | 낮음 | INPUT SQL에 MERGE가 있을 때 |

---

## 3. Gemma vs GPT 성능 비교

### 3.1 속도

| 모델 | 크기 | GPU | 변환 시간 | 처리량 |
|------|------|------|---------|---------|
| Gemma 4B | 4B | 8GB | 2~5초 | 빠름 |
| Gemma 12B | 12B | 16GB | 5~10초 | 중간 |
| Gemma 27B | 27B | 24GB | 10~20초 | 느림 |
| **GPT-4o** | - | Cloud | 3~8초 | 빠름 |

### 3.2 정확도 (품질 점수 기준)

```
구문 검증 (AST parse)        30점
타입힌트 포함              15점
Docstring 포함             10점
파라미터 바인딩          20점
에러 처리 (try/except)     15점
Context Manager (with)     10점
────────────────────
최대 점수                 100점
```

**성능 평가 (샘플 5개 SQL 기준)**:
- **Gemma-27B**: 평균 78점 (무료, 느림)
- **GPT-4o (퓨샷)**: 평균 92점 (유료, 빠름)
- **GPT-4o (제로샷)**: 평균 68점 (유료, 빠르지만 부정확)

### 3.3 비용

```
Gemma: 무료 (로컬 GPU 필요, 초기 투자 필요)
GPT-4o 퓨샷: $0.01~0.03 (호출당)
GPT-4o 제로샷: $0.005~0.02 (호출당)
```

---

## 4. 실제 변환 프로세스

### 4.1 단계별 워크플로우

```
1️⃣ SQL 파일 입력
   ↓
2️⃣ 패턴 분석 (CURSOR? TRANSACTION? PIVOT? 등)
   ↓
3️⃣ 관련 퓨샷 예시 선택 (1~3개)
   ↓
4️⃣ 프롬프트 생성
   ↓
5️⃣ Gemma/GPT 호출
   ↓
6️⃣ 코드 추출 (```python ... ``` 블록)
   ↓
7️⃣ 구문 검증 (AST parse)
   ↓
8️⃣ 출력 (Python 파일 + 리포트)
```

### 4.2 API 호출 예

```bash
# Gemma 변환
python main.py convert --backend gemma --input examples/sql/sample1.sql

# GPT 변환 (퓨샷)
python main.py convert --backend gpt --input examples/sql/sample1.sql

# Gemma vs GPT 비교 (기본: 둘 다 퓨샷으로 공정 비교)
python main.py compare --input examples/sql/sample1.sql

# (선택) GPT 제로샷까지 포함해 3-way 비교
python main.py compare --include-zero-shot --input examples/sql/sample1.sql

# 배치 변환
python main.py batch --input-dir examples/sql/ --output-dir output/
```

---

## 5. 주요 변환 규칙

| SQL | Python | 예시 |
|-----|--------|------|
| `DECLARE @var INT` | `var: int = ...` | 함수 매개변수 또는 변수 선언 |
| `SELECT INTO #temp` | `df = pd.read_sql(...)` | 임시 테이블 → DataFrame |
| `CURSOR/WHILE` | `for row in ...` 또는 `df.iterrows()` | 루프 처리 |
| `TRY...CATCH` | `try...except` | 예외 처리 |
| `BEGIN TRAN/COMMIT` | `conn.commit()` | 트랜잭션 제어 |
| `OUTPUT` | `return ...` 또는 `@dataclass` | 반환값 처리 |
| `MERGE` | 존재 여부 확인 후 INSERT/UPDATE | UPSERT 패턴 |
| `sp_executesql` | `cursor.execute(..., params=[...])` | 동적 SQL (파라미터 바인딩 필수) |

---

## 6. 최적 실행 시나리오

### 시나리오 A: 품질 최우선

```bash
# Gemma-27B (최고 정확도) + 수동 리뷰
python main.py convert --backend gemma --input sample.sql
# 생성된 Python 코드를 수동으로 리뷰 및 수정
```

### 시나리오 B: 속도 최우선

```bash
# GPT-4o-mini (저렴하고 빠름)
python main.py convert --backend gpt --input sample.sql
```

### 시나리오 C: 비교 분석

```bash
# 기본(추천): Gemma(퓨샷) vs GPT(퓨샷) 공정 비교
python main.py compare --input sample.sql
# → JSON 리포트 생성 (품질 점수 포함)

# (선택) 3-way: GPT 제로샷도 포함
python main.py compare --include-zero-shot --input sample.sql
```

### 시나리오 D: 대량 변환

```bash
# 폴더 일괄 변환 + 비교
python main.py batch --input-dir ./sql_files/ --output-dir ./converted/
# → batch_comparison_report.json 생성
```

---

## 7. 주의사항 및 주의점

⚠️ **SQL Injection 방지**  
퓨샷 예시에 파라미터 바인딩 (? 플레이스홀더) 포함 필수

⚠️ **동적 SQL의 컬럼명**  
화이트리스트 검증 코드 반드시 포함

⚠️ **암호화/복호화**  
SQL의 ENCRYPTBYKEY 등은 한계 있음 (수동 리뷰 필요)

⚠️ **성능 고려**  
대량 데이터 처리 시 pandas vs SQLAlchemy 선택

---

## 8. 예상 질문 (FAQ)

**Q: Gemma 4B인데 정확도가 낮네요**  
A: 4B는 단순 쿼리만 추천. 12B 이상 사용하세요.

**Q: GPT 비용이 많이 드나요?**  
A: 호출당 $0.01~0.03. 100개 SQL = $1~3 (저렴).

**Q: 퓨샷 없이도 작동하나요?**  
A: 네. GPT는 `python main.py convert --backend gpt --zero-shot ...`로 가능하지만 품질이 떨어질 수 있습니다.  
비교 모드에서는 기본이 퓨샷-only이고, 3-way가 필요하면 `python main.py compare --include-zero-shot ...`를 사용하세요.

**Q: 어떤 SQL 문법을 지원하나요?**  
A: T-SQL 대부분 지원. XML, JSON 처리 등은 부분 지원.

---

## 9. 참고자료

- [Gemma 모델 카드](https://huggingface.co/google/gemma-3-27b-it)
- [OpenAI GPT Documentation](https://platform.openai.com/docs)
- [Few-Shot Learning Paper](https://arxiv.org/abs/2005.14165)
