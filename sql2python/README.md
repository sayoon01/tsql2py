# SQL2Python

MS SQL Server 저장 프로시저를 Python 코드로 변환하는 CLI 도구입니다.  
**Ollama**로 `config.yaml`의 세 `model_name`(예: `gemma3:12b`, `qwen2.5-coder:14b`, `glm-4.7-flash:Q4_K_M` 등)을 같은 퓨샷 조건에서 **3-way 비교**합니다.

---

## 설치

```bash
cd sql2python    # 저장소 루트에서 sql2python 디렉터리로 이동
pip install -r requirements.txt
```

### 필수 환경

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** 설치 후 데몬 실행 (`ollama serve`, 기본 `http://localhost:11434`)
- `config.yaml`에 적힌 태그와 동일하게 모델 pull (예):

```bash
ollama pull gemma3:12b
ollama pull qwen2.5-coder:14b      # config.yaml qwen.model_name 과 동일
ollama pull glm-4.7-flash:Q4_K_M   # config.yaml glm.model_name 과 동일
```

설치 후 **`ollama list`에 표시된 문자열**이 `config.yaml`의 `gemma` / `qwen` / `glm` 의 `model_name` 과 **한 글자도 다르면 안 됩니다.**  
양자화 태그(`:Q4_K_M` 등)를 쓰는 변형은 **이름이 다른 모델**이므로, pull한 태그와 YAML을 함께 맞추세요.

서버 주소를 바꾸려면 `config.yaml`의 `ollama.host`를 수정합니다.

`requirements.txt` 에 **Comparator 차트**용 `matplotlib`, `numpy` 가 포함되어 있습니다 (`compare` / `batch` 실행 시 모듈 로드에 사용).

> **GPT(OpenAI)** 는 기본 비활성입니다. 쓰려면 `config.yaml`에서 `gpt:` 블록 주석을 해제하고 `OPENAI_API_KEY`를 설정한 뒤, `converters/gpt_converter.py` 및 `main.py`를 GPT 경로에 맞게 연결해야 합니다. 현재 CLI는 **Ollama 전용**입니다.

---

## 사용법

작업 디렉터리는 **`sql2python/`** (`main.py`가 있는 곳) 기준입니다.

```bash
cd sql2python

# 단일 변환 (백엔드: gemma | qwen | glm)
python main.py convert --backend gemma \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --num-examples 10

# 3-way 비교 (Gemma vs Qwen vs GLM, 동일 퓨샷 개수)
python main.py compare \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --num-examples 10

# 비교 + 리포트 차트 PNG (--plots 시 output-dir/report/ 에 저장)
python main.py compare \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --output-dir output \
  --num-examples 10 \
  --plots

# 배치: 디렉터리 내 *.sql 전부 변환 + 파일마다 3-way 비교
python main.py batch \
  --input-dir examples/sql/ \
  --num-examples 10

# 배치 + 차트
python main.py batch \
  --input-dir examples/sql/ \
  --output-dir output \
  --num-examples 10 \
  --plots

# 프롬프트만 미리보기 (모델 호출 없음)
python main.py preview \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --backend gemma \
  --num-examples 10

# 변환된 Python 파일 코드 품질 분석 (모델 호출 없음)
python main.py analyze \
  --input output/usp_add_authorbook_storebook_gemma3_12b.py \
  --model gemma3:12b

# 원본 SQL 포함 시 함수명 보존 여부도 함께 확인
python main.py analyze \
  --input output/usp_add_authorbook_storebook_gemma3_12b.py \
  --sql  examples/sql/usp_add_authorbook_storebook.sql \
  --model gemma3:12b
```

---

## 추천 워크플로우

1. **단일 파일** `compare`로 퓨샷 개수(예: 3 → 10)를 조절해 품질을 본 뒤  
2. **`batch`** 로 같은 설정을 전체 SQL에 적용합니다.  
3. 변환 후 **`analyze`** 로 저장된 Python 파일의 품질 점수를 재확인할 수 있습니다.

| `--num-examples` | 용도 |
|------------------|------|
| 3 | 빠른 테스트, 토큰 절약 |
| 5 | 균형 |
| 목록 길이까지 | 예시 풀 전부 (`few_shot_examples.yaml` → `ALL_EXAMPLES` 앞에서 N개; 현재 11개) |

### `analyze` 점수 기준

| 검사 항목 | 배점 |
|-----------|------|
| Python 구문 유효 (AST 파싱) | +30 |
| 파라미터화 쿼리 (`?` 바인딩) | +15 |
| `try/except` 포함 | +10 |
| `with pyodbc.connect(...)` | +10 |
| `commit` 포함 | +10 |
| `rollback` 포함 | +10 |
| 플레이스홀더 개수 일치 | +10 |
| 위험 패턴 없음 (`@@error`, `lastrowid` 등) | +5 |
| **최대** | **100** |

---

## 프롬프트·퓨샷·후처리 역할

변환 품질은 세 겹으로 나뉩니다. 서로 역할이 다르며, **퓨샷과 시스템 지침이 완전히 같은 문장일 필요는 없고**, 모순만 없으면 됩니다.

### `template.py` — `SYSTEM_INSTRUCTION`

- 모델에게 **“어떻게 변환해야 하는지”** 를 가르치는 **범용 규칙** 모음입니다.
- T-SQL → Python 대응, 출력 형식(코드만), pyodbc·금지 DB, 트랜잭션·DML 처리 원칙 등 **모든 SQL 패턴에 공통으로 적용**되는 원칙을 둡니다.
- **퓨샷 예시 YAML과 논리적으로 모순되지 않으면 충분**합니다. 예시와 글자 수까지 맞출 필요는 없습니다.

### 퓨샷 예시 — `prompts/few_shot_examples.yaml`

- 모델에게 **“이런 스타일·구조로 써라”** 를 **구체적으로 보여줍니다** (`tag`, `sql`, `python`).
- **패턴 다양성**이 핵심입니다. (단순 조회, DML+커밋, 트랜잭 분기, 동적 SQL, MERGE, 소프트 삭제 등)
- **스타일**(pyodbc, `?` 바인딩, dataclass 반환, 에러 처리 톤 등)은 일관되게, **도메인**(테이블·업무 시나리오)은 서로 다르게 두는 것이 좋습니다.

### `post_process.py`

- 모델이 낸 코드에서 **명백히 잘못된 Python 관용구·누락**만 짧게 고칩니다.
- **SQL 의미·프로시저 구조**는 후처리로 바꾸지 않습니다.
- 입력 SQL별 특수 케이스가 아니라, **여러 변환에 공통으로 쓸 수 있는 교정**만 유지합니다.

---

## 프로젝트 구조

```
sql2python/
├── main.py                     # CLI (convert / compare / batch / preview)
├── config.yaml                 # Ollama 모델명·생성 파라미터·ollama.host
├── requirements.txt
├── prompts/
│   ├── few_shot_examples.yaml # 퓨샷 SQL/파이썬 쌍 (examples 리스트)
│   ├── few_shot_examples.py   # 위 YAML 로드 → ALL_EXAMPLES
│   ├── template.py            # 프롬프트 빌더 (백엔드 공통 텍스트 프롬프트)
│   └── post_process.py        # 생성 코드 후처리
├── converters/
│   ├── ollama_converter.py    # ★ 실제 사용: Ollama HTTP API 추론
│   ├── comparator.py         # 3-way 품질 점수·리포트
│   ├── gpt_converter.py      # OpenAI용 (기본 미연동)
│   ├── gemma_converter.py    # 레거시: HuggingFace 직접 로드 (현재 main 미사용)
│   ├── qwen_converter.py     # 레거시: HF (현재 main 미사용)
│   └── glm_converter.py      # 레거시: HF (현재 main 미사용)
├── examples/sql/
└── output/                     # 변환 결과 (git 무시 권장)
```

### 모듈 요약

| 파일 | 역할 |
|------|------|
| **main.py** | `OllamaConverter`로 gemma/qwen/glm 순차 호출, `Comparator.generate_report`, `--plots` 시 차트 |
| **config.yaml** | 각 백엔드별 `model_name`, temperature, top_p, `max_new_tokens` 등 |
| **ollama_converter.py** | `build_gemma_prompt` + Ollama 스트림/폴백, `post_process_python`, 구문 오류 시 재시도 |
| **comparator.py** | 품질 점수·winner·`comparison_report.json` / `batch_report.json`, 선택 시 `report/*.png` |
| **gemma / qwen / glm_converter.py** | 예전 HF 파이프라인; **삭제 후보**. `main.py`는 사용하지 않음 |

---

## 실행 흐름 (요약)

**convert**  
`config.yaml` 로드 → 선택 백엔드의 `model_name`으로 `OllamaConverter` → `template.SYSTEM_INSTRUCTION` + 퓨샷 N개로 프롬프트 구성 → 응답에서 Python 추출 → `post_process_python` → `output/`

**compare / batch**  
각 파일에 대해 `gemma` → `qwen` → `glm` 순으로 같은 `num_examples`로 변환 → 콘솔 표 + JSON 리포트.  
`--plots` 이면 `output-dir/report/`에 `overall.png`, `metrics.png`, `scatter.png`, `table.png` 추가.

---

## Comparator 사용법 (`converters/comparator.py`)

변환 직후 나오는 **Ollama 결과 dict**(`python_code`, `elapsed_sec`, `output_tokens`, `model` 등)를 묶어 점수·승자·리포트·(선택) 차트를 냅니다.

### CLI에서 (권장)

- **`compare`**: `--output-dir` 아래 `comparison_report.json`. **`--plots`** 이면 **같은 디렉터리의 `report/`** 에 PNG 네 장 (`overall`, `metrics`, `scatter`, `table`).
- **`batch`**: `batch_report.json` 과 동일 규칙 (`<output-dir>/report/`).

### JSON에 넣는 데이터 형식 (`batch_results` 등)

`main.py`의 `batch`가 쌓는 리스트와 **같은 형태**이면 됩니다.

```python
batch_results = [
    {
        "file": "usp_add_authorbook_storebook.sql",
        "gemma": { "python_code": "...", "elapsed_sec": 1.2, "output_tokens": 100, "model": "gemma3:12b" },
        "qwen":  { "python_code": "...", "elapsed_sec": 1.0, "output_tokens": 95,  "model": "qwen2.5-coder:14b" },
        "glm":   { "python_code": "...", "elapsed_sec": 2.0, "output_tokens": 200, "model": "glm-4.7-flash:Q4_K_M" },
    },
    # ... 다른 SQL 파일
]
```

`file`은 표시용 이름이며, `gemma` / `qwen` / `glm` 값은 **`OllamaConverter.convert()` 또는 `convert_file()` 반환 dict**를 그대로 넣으면 됩니다.

### Python에서 직접 호출

```python
from pathlib import Path
from converters.comparator import Comparator

comp = Comparator()

# (1) dict 리스트 → ComparisonResult 로 정규화 후 점수만 JSON
normalized = Comparator._normalize_results(batch_results)
comp.save_json(normalized, Path("report/result.json"))

# (2) 요약 + 막대/지표/산점도/표 PNG
comp.plot_all(normalized, outdir="report")

# (3) main과 동일한 통합 리포트 (summary + details) + 선택적 차트
comp.generate_report(
    batch_results,
    Path("output/batch_report.json"),
    with_plots=True,  # True면 output/batch_report.json 기준 → output/report/*.png
)
```

- **`compare()`**: 한 건 비교. 인자는 `gemma_result=`, `qwen_result=`, `glm_result=` 에 각 백엔드의 변환 dict.
- **`build_summary()`**: `list[ComparisonResult]` → 모델별 평균 점수·시간·토큰·승률 등.
- **`save_json()`**: `ComparisonResult` 리스트만 직렬화 (파일별 점수·winner).

의존성: 차트를 쓰려면 `matplotlib`, `numpy`가 필요합니다 (`requirements.txt`에 포함).

---

## 퓨샷 예시 (`prompts/few_shot_examples.yaml`)

`few_shot_examples.py`가 시작 시 YAML을 읽어 `ALL_EXAMPLES`를 만듭니다. 키 `examples` 아래에 `tag`, `sql`, `python`이 있는 객체를 **순서대로** 넣습니다. `--num-examples`는 **1 ~ 목록 길이**까지, 앞에서부터 잘라 프롬프트에 붙입니다.

| `tag` | 패턴 요약 |
|-------|-----------|
| `simple_select` | 파라미터·TOP·SELECT |
| `simple_dml_update` | 단일 UPDATE + commit/rollback 스타일 |
| `transaction` | TRY/CATCH·트랜잭션·다문 DML |
| `temp_table` | 임시 집계·일괄 UPDATE |
| `dynamic_sql` | 검증·화이트리스트·페이징 |
| `merge_upsert` | UPDATE 후 없으면 INSERT |
| `soft_delete` | 논리 삭제·이력 |
| `bulk_insert` | 다건·중복 제외 |
| `scalar_aggregate` | OUTPUT/집계 한 덩어리 |
| `multiple_resultset` | 연속 결과셋 |
| `cte_ranking` | CTE·`ROW_NUMBER`·Top-N |

새 예시를 넣을 때는 위 절(스타일 일관·도메인 다양)을 참고하면 됩니다.

---

## 품질 점수 (`comparator.py`)

| 항목 | 점수 |
|------|------|
| 구문 유효 (AST) | +30 |
| 파라미터 바인딩 (`?`) | +20 |
| 타입힌트 | +15 |
| 에러 처리 | +15 |
| docstring | +10 |
| Context Manager (`with`) | +10 |
| **합계** | **100** |

---

## 예제 SQL (`examples/sql/`)

BookStore용 `usp_*.sql` 샘플(수정·추가·삭제·연결 등)을 둡니다.

---

## 수정·정리 요약 (코드베이스 기준)

| 구분 | 내용 |
|------|------|
| **신규** | `ollama_converter.py` — Ollama 단일 경로, 후처리·재시도 |
| **신규** | `comparator.py` — 점수·winner·JSON·matplotlib 차트, `generate_report(..., with_plots=)` |
| **수정** | `config.yaml` — `gemma` / `qwen` / `glm` / `ollama.host` |
| **수정** | `main.py` — `compare` / `batch` 에 `--plots` 옵션 |
| **삭제 가능** | `gemma_converter.py`, `qwen_converter.py`, `glm_converter.py` (HF, 미사용) |

---

## 라이선스

MIT
