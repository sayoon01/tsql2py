# SQL2Python

MS SQL Server 저장 프로시저를 Python 코드로 자동 변환하는 도구입니다.
Gemma (퓨샷 프롬프팅) + GPT 비교 기능을 제공합니다.

## 설치

```bash
pip install -r requirements.txt
```

### 필수 환경
- Python 3.10+
- CUDA GPU (Gemma 사용 시): 27B → 24GB+, 12B → 16GB+, 4B → 8GB+
- OpenAI API 키 (GPT 비교 사용 시)

```bash
export OPENAI_API_KEY="sk-..."
export HF_TOKEN="hf_..."  # HuggingFace (Gemma 접근용)
```

## 사용법

```bash
# 단일 파일 변환 (Gemma)
python main.py convert --backend gemma --input examples/sql/sample1_simple_select.sql

# 단일 파일 변환 (GPT)
python main.py convert --backend gpt --input examples/sql/sample1_simple_select.sql

# Gemma vs GPT 비교 (기본: 둘 다 퓨샷으로 공정 비교)
python main.py compare --input examples/sql/sample2_transaction_audit.sql

# (선택) GPT 제로샷까지 포함해 3-way 비교
python main.py compare --include-zero-shot --input examples/sql/sample2_transaction_audit.sql

# 전체 SQL 일괄 변환 + 비교
python main.py batch --input-dir examples/sql/ --output-dir output/

# (선택) 배치에서도 GPT 제로샷 포함
python main.py batch --include-zero-shot --input-dir examples/sql/ --output-dir output/

# 프롬프트 미리보기 (모델 호출 없이)
python main.py preview --input examples/sql/sample1_simple_select.sql --backend gemma

# GPT 프롬프트 미리보기(메시지 전체 출력). 길면 --max-chars로 제한 가능
python main.py preview --input examples/sql/sample1_simple_select.sql --backend gpt --max-chars 0
```

## 추천 워크플로우 (단일 파일 → 배치)

실제 대량 변환 전에, **단일 파일 비교로 프롬프트/옵션/품질을 먼저 고정**한 뒤 `batch`로 확장하는 걸 권장합니다.

### 1) 단일 파일 비교 (공정 비교: 둘 다 퓨샷)

```bash
python main.py compare \
  --input examples/sql/sample2_transaction_audit.sql \
  --num-examples 4 \
  --output-dir output/
```

### 2) (선택) 단일 파일 3-way 비교 (GPT 제로샷 포함)

```bash
python main.py compare \
  --include-zero-shot \
  --input examples/sql/sample2_transaction_audit.sql \
  --num-examples 4 \
  --output-dir output/
```

### 3) 배치 비교 (공정 비교: 둘 다 퓨샷)

```bash
python main.py batch \
  --input-dir examples/sql/ \
  --num-examples 4 \
  --output-dir output/
```

### 4) (선택) 배치 3-way 비교 (GPT 제로샷 포함)

```bash
python main.py batch \
  --include-zero-shot \
  --input-dir examples/sql/ \
  --num-examples 4 \
  --output-dir output/
```

## 프로젝트 구조

```
sql2python/
├── main.py                  # CLI 진입점
├── config.yaml              # 모델/생성 파라미터 설정
├── requirements.txt
├── prompts/
│   ├── few_shot_examples.py # 퓨샷 예시 5개 (패턴별)
│   └── template.py          # Gemma/GPT 프롬프트 빌더
├── converters/
│   ├── gemma_converter.py   # HuggingFace Gemma 변환기
│   ├── gpt_converter.py     # OpenAI GPT 변환기
│   └── comparator.py        # 품질 분석 및 비교 엔진
├── examples/sql/            # 테스트용 SQL 프로시저
└── output/                  # 변환 결과 저장
```

### 각 모듈의 역할

| 파일/모듈 | 역할 |
|-----------|------|
| **main.py** | CLI 진입점 (@click 기반). 4가지 커맨드 제공: `convert`, `compare`, `batch`, `preview` |
| **config.yaml** | 모델 이름, 랜덤성 정도(temperature: 0~1), 최대 토큰 수 등 설정 |
| **prompts/template.py** | SQL → 프롬프트 변환. Gemma 및 GPT용 프롬프트 템플릿 관리 |
| **prompts/few_shot_examples.py** | 5가지 SQL 패턴별 퓨샷 예시 저장 (CRUD, 트랜잭션, 커서 등) |
| **converters/gemma_converter.py** | HuggingFace Gemma 모델로 변환 실행 |
| **converters/gpt_converter.py** | OpenAI GPT 모델로 변환 실행 |
| **converters/comparator.py** | Gemma vs GPT 결과 비교 및 품질 점수 계산 |

### 실행 흐름

#### 1️⃣ **단일 변환 (Convert)**
```
main.py (CLI 입력)
  ↓
config.yaml (설정 로드)
  ↓
[Gemma 또는 GPT 선택]
  ├─ Gemma 경로:
  │  ├ prompts/template.py → Gemma 프롬프트 빌드
  │  ├ prompts/few_shot_examples.py → num_examples개 예시 선택
  │  └ converters/gemma_converter.py → 모델 실행
  │
  └─ GPT 경로:
     ├ prompts/template.py → GPT 메시지 빌드
     ├ prompts/few_shot_examples.py → 퓨샷 예시 (optional)
     └ converters/gpt_converter.py → API 호출
  ↓
output/ 디렉토리에 Python 코드 저장
```

#### 2️⃣ **비교 변환 (Compare)**
```
main.py (compare 커맨드)
  ↓
[기본: 퓨샷-only 비교]
  ├─ Gemma 변환 (퓨샷)
  └─ GPT 변환 (퓨샷)
  (선택) --include-zero-shot이면 GPT 제로샷도 추가 실행
  ↓
converters/comparator.py (품질 비교)
  ├─ 구문 검증 (AST parse)
  ├─ 기능 마킹 (타입힌트, docstring 등)
  └─ 품질 점수 계산 (0~100)
  ↓
비교 결과 표 + JSON 리포트 출력
```

## 퓨샷 예시 (5가지 패턴)

### 1. 단순 SELECT (파라미터 + 기본값)
```
SQL: CREATE PROCEDURE GetActiveUsers @MinAge INT = 18
Python: def get_active_users(min_age: int = 18) -> pd.DataFrame:
```

### 2. 트랜잭션 + OUTPUT 파라미터 + TRY/CATCH
```
SQL: BEGIN TRANSACTION / COMMIT / ROLLBACK
Python: try/except + conn.commit() / conn.rollback()
```

### 3. 임시 테이블 + 커서 루프
```
SQL: CREATE TABLE #Temp / CURSOR / WHILE @@FETCH_STATUS
Python: pandas DataFrame + iterrows() / 벡터화 연산
```

### 4. 동적 SQL + 페이징
```
SQL: sp_executesql / OFFSET...FETCH
Python: f-string SQL + pandas.read_sql() with params
```

### 5. MERGE (UPSERT)
```
SQL: MERGE INTO
Python: 존재 확인 후 INSERT 또는 UPDATE
```

## 성능 주의사항

- **Gemma 4B**: 빠르지만 정확도 낮음 (간단한 쿼리용)
- **Gemma 12B**: 균형잡힌 성능 (추천)
- **Gemma 27B**: 가장 정확하지만 GPU 메모리 필요 (24GB+)
- **GPT-4o**: 가장 손실 없음, 비용 발생 (0.01~0.03 USD/호출)
- **GPT-4o-mini**: 저렴하지만 정확도 낮음

## 라이선스

MIT
