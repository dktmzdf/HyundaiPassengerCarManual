# AvanteManualRAG

2025 아반떼 N DCT(`CN7N/2025/dct`) 매뉴얼을 로컬에서 파싱하고,
OpenAI `text-embedding-3-small`(1536차원) + FAISS로 검색한 뒤
`gpt-5-mini` Responses API로 근거와 페이지를 붙여 답하는 Python CLI야.

현재는 대표 매뉴얼 한 권과 검토 완료한 일부 영역의 기준선이야. 전체 페이지를 추출했다고
전체 내용을 검증한 것은 아니야. 상태·제외 영역은 모든 검색/답변의 `coverage`로 확인해.
웹 UI, 전체 차종 처리, 자동 OCR, 그림 해석은 포함하지 않아. **원본 PDF는 배포하지 않아.**

## 설치

Windows / Python **3.11.9**에서 검증했어. 지원 범위는 `>=3.11,<3.12`야.
프로젝트 루트에서 PowerShell로 실행해.

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
.venv/Scripts/python.exe -m avante_manual_rag.cli --help
```

직접 의존성은 pdfplumber 0.11.10, openai 3.26.0, faiss-cpu 1.15.1,
numpy 2.4.6, tiktoken 0.14.0이야. pytest 9.1.1과 reportlab 5.0.1은 개발용이야.
전이 의존성까지 `requirements.lock`에 고정했어. 다른 OS/Python 조합은 미검증이야.

## 설정과 실행

`config.example.toml`이 기본 설정이야. 바꾸려면 `config.local.toml`로 복사하고
명령 앞에 `--config config.local.toml`을 붙여. 경로는 설정 파일 위치를 기준으로 해석해.

프로젝트 루트의 **로컬 `.env`**에 아래 이름을 설정해. 실제 키를 Git이나 대화에 넣지 마.
환경변수가 있으면 `.env`보다 우선해. `.env` 로더는 이 두 변수만 읽고 문자열을 실행하거나
변수 치환하지 않아. 인라인 주석 없이 한 줄에 하나씩 적어.

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_CHAT_MODEL=gpt-5-mini
```

생성 기본 모델은 사용자 선택인 `gpt-5-mini`야. 설정 파일에서도 바꿀 수 있지만
이번에 검증한 생성 옵션은 이 모델 기준이야. 다른 모델은 Responses/Structured Outputs,
reasoning 옵션과 tokenizer 호환성을 다시 확인해야 해.

```powershell
.venv/Scripts/python.exe -m avante_manual_rag.cli ingest --pages 6,13,16,200,205,207-208,212
.venv/Scripts/python.exe -m avante_manual_rag.cli ingest
.venv/Scripts/python.exe -m avante_manual_rag.cli index
.venv/Scripts/python.exe -m avante_manual_rag.cli search "DCT 기어오일 용량과 사양은?"
.venv/Scripts/python.exe -m avante_manual_rag.cli ask "DCT 기어오일 용량과 사양은?"
```

`ingest`는 키 없이 가능해. `index`는 청크 임베딩 캐시가 없으면 API를 호출해.
`search`는 생성 모델을 호출하지 않지만 새로운 질문의 임베딩에는 키가 필요해.
같은 텍스트·모델·차원·전처리의 캐시는 재사용해. `ask`는 검색 후 생성 API를 호출해.
첫 tiktoken 실행은 공식 tokenizer 파일을 받아 `data/cache/tiktoken`에 캐시하므로
네트워크가 필요할 수 있어. 기본 테스트는 이 다운로드도 하지 않아.

정상 명령은 JSON과 종료 코드 0, 실패는 stderr의 안전한 오류 코드와 0이 아닌 종료 코드를 반환해.
질문 전문·원문·인증 헤더를 진단 로그로 남기지 않아. 명시적으로 요청한 검색/답변 결과에는
질문에 필요한 발췌가 출력돼. 기본적으로 대화 내역은 저장하지 않아.

## 원본과 파싱 검토

직접 보유한 PDF와 CSV manifest를 `data/raw/hyundai/passenger/`에 준비해.
manifest 필드는 `category,model,project_code,model_year,filename,source_url,language,
downloaded_on,size_bytes,sha256`이야. 등록 시 차량, 연식, 크기, SHA-256을 확인해.
대표 파일은 `CN7N_2025_ko_KR.pdf`, 436페이지,
SHA-256 `87bbeec00684414edc31658bd0e104d714b35dab8fa8a46f68c35715a740bb0a`야.
manifest의 출처 URL은 이번 접근 검사에서 열리지 않아 `unverified`로 기록했고 인용 링크로
내보내지 않아. 주소를 추측해서 보정하지 않았어.

pdfplumber는 텍스트·좌표·표를 추출하고 표와 겹치는 본문을 제거해. 인쇄 번호는 footer에서
명확한 `장-쪽` 패턴 하나가 확인될 때만 사용해. 빈 추출은 자동으로 빈 페이지라 판단하지 않아.
`needs_ocr`, `needs_review`, `failed`, `not_processed`를 따로 기록해.

**검토 전 블록은 `unknown`이며 색인하지 않아.** `data/reviews/cn7n-2025.json`은 원본 해시에
묶인 로컬 영역 검토 파일이야. 현재 보유한 로컬 검토 파일은 PDF 13(인쇄 1-7), 16(1-10),
205(6-13), 207(6-15), 208(6-16), 212(6-20)의 일부 영역과 빈 PDF 6을 확인한 결과야.
다단 본문은 각 열을 따로 crop하고, 혼합 표는 수동/DCT 행을 분리했어.
DCT의 수동 변속 모드는 `dct`로 분류해. 수동변속기 차량과 다른 개념이야.

검토 파일이 없으면 추출은 가능하지만 검토된 청크가 없어서 `index`는 실패해.
원문을 포함하는 검토 파일도 배포에서 제외하므로 새 설치에서는 직접 검토해야 해.
검토 형식은 다음과 같아. bbox는 PDF 좌상단 기준 point 단위야.

```json
{
  "document_id": "원본 SHA-256",
  "pages": {
    "1": {
      "printed_page": "1-1",
      "reason": "시각 비교 결과와 적용 범위 판단 근거",
      "regions": [{
        "id": "unique-region-id", "bbox": [20, 30, 200, 400],
        "kind": "text", "section": "절 제목", "applicability": "dct",
        "conditions": [], "warnings": [], "related_ids": []
      }]
    }
  }
}
```

`applicability`는 `common/dct/manual/unknown` 중 하나야. 변속기 언급이 없다는 이유만으로
`common`으로 지정하면 안 돼. 표는 `table` 배열 또는 검토한 `corrected_text`로 머리글·단위를
보존하고, `related_ids`로 다른 페이지의 각주/경고를 연결해. 보정은 렌더링 원문과 대조해야 해.
추출 실패 페이지와 그림 의존 구간은 검토 완료로 꾸미지 마. 지나치게 긴 근거는 임의로 자르지
않고 임베딩 한도 오류로 알리므로, 표의 필수 맥락을 유지하도록 검토 영역을 나눠야 해.

## 저장 구조와 복구

| 경로 | 역할 |
| --- | --- |
| `src/avante_manual_rag/ingestion.py` | CSV 등록과 원본 검증 |
| `parsing.py`, `chunking.py` | PDF 어댑터, 검토 적용, 결정적 청크 |
| `openai_adapter.py`, `retrieval.py` | API 호출·벡터 캐시·FAISS 검색 |
| `answering.py` | 구조화 생성·발췌·수치/단위·인용 검증 |
| `storage.py`, `contracts.py`, `config.py` | 저장, 공통 데이터 계약, 설정 |
| `pipeline.py`, `cli.py`, `evaluation.py` | 실행 연결, CLI, 평가 |
| `data/processed/parsed/<generation>/` | 문서·페이지·처리 상태 JSON |
| `data/processed/indexes/<generation>/` | FAISS 및 청크 매핑 JSON |
| `data/processed/cache/` | 임베딩 캐시 |
| `data/processed/reports/<generation>/` | 로컬 평가 상세 및 공유 요약 |
| `data/reviews/` | 렌더링·검토·보정·출처 검사 기록 |

각 세대는 새 디렉터리에 만들고 검증 후 `active.json` 하나를 원자적으로 교체해.
여러 파일 자체를 한 번에 교체하는 트랜잭션은 아니야. 실패한 새 세대는 활성화하지 않고
이전 세대가 남아. 해시는 우발적 손상 검사용이며 악성 파일의 진위 인증이 아니야.
FAISS는 **직접 생성한 신뢰 가능한 로컬 파일만** 읽어. pickle은 사용하지 않아.
출력 경로 탈출과 디렉터리 링크를 통한 탈출도 거부해.

```powershell
.venv/Scripts/python.exe -m avante_manual_rag.cli rollback parsed <이전-파싱-세대-ID>
.venv/Scripts/python.exe -m avante_manual_rag.cli rollback indexes <대응하는-색인-세대-ID>
```

파서/검토/청크 설정을 바꾸면 다시 `ingest`, `index`를 실행해. 현재 파싱과 색인의 설정이
다르면 검색을 거부해. 임베딩 모델·차원·전처리를 바꾸면 벡터와 색인을 새로 생성해야 해.
이 기준선은 요청된 모델/1536차원을 검증하므로 다른 임베딩 설정은 거부해.
생성 모델/프롬프트 변경은 색인을 재사용할 수 있지만 답변 평가는 다시 해야 해.

## 모델 호출·인용·비용

FAISS `IndexFlatIP`에 L2 정규화한 float32 벡터를 저장하고 질문도 같은 방식으로 정규화해.
내적이 cosine 유사도에 해당하지만 **정답 확률이 아니야**. 색인 생성 전에 차량 프로필과
공통/DCT 적용 범위를 거르므로 수동·미확인·다른 연식 청크가 답변 근거로 섞이지 않아.

생성은 Responses `store=false`, 비스트리밍, strict JSON Schema를 사용해. 추론 강도는 low,
최대 출력은 추론 토큰을 포함해 4000토큰이야. 반환받은 주장을
검색 ID에 연결하고 발췌가 실제 원문에 있는지 검사해. PDF 줄바꿈 공백만 달라진 발췌는 원래
원문 span으로 복원해. 수치/단위를 바꾸거나 근거 ID를 만들면 실패해. 경고와 조건은 저장된
근거에서 직접 붙여. 이는 형식·발췌 검사이며 **문장 전체의 의미적 뒷받침을 증명하지는 못해**.
검색된 문서 안의 지시문은 시스템 지시가 아니라 참고 데이터로 전달해.

`answered`, `insufficient_evidence`, `needs_clarification`, `conflicting_evidence`와
`retrieval_error`, `generation_error`, `citation_validation_error`를 구분해.
API 장애를 “매뉴얼에 답이 없다”로 바꾸지 않아. 부족 응답도 현재 검색·검토 범위에 한정해.
요청 timeout 30초, 각 API 작업 deadline 120초, SDK 자체 재시도 0회,
어댑터 재시도 최대 2회야. 인증/입력/할당량 소진은 재시도하지 않아.

임베딩에는 색인 청크와 질문이, 생성에는 질문과 검색 근거가 OpenAI로 전송돼.
원본 PDF 파일은 로컬에 남고 Files API에는 업로드하지 않아. `store=false`가 모든 서비스
보관을 없애는 보장은 아니야. [OpenAI 데이터 제어 문서](https://developers.openai.com/api/docs/guides/your-data)를 확인해.
usage에는 요청/응답 모델명과 입력·출력 토큰을 기록해. 실제 비용은 모델 단가와 usage에 따라
달라져. 임베딩 캐시는 재색인의 중복 요청을 줄이지만 생성 결과 캐시는 없어서 `ask`마다
생성 비용이 생겨. 단가는 [공식 가격표](https://openai.com/api/pricing/)를 확인해.

| 선택 | 장점 | 비용과 한계 |
| --- | --- | --- |
| 채택: OpenAI SDK 직접 호출 + FAISS | 설치와 흐름이 작고 API 동작을 직접 제어 | 네트워크·사용료·텍스트 외부 전송 필요 |
| 대안: LangChain + FAISS | 다양한 로더·retriever·모델 인터페이스 활용 | 현재 작은 범위에는 추상화와 버전 의존성이 추가됨 |
| 대안: 로컬 임베딩/생성 모델 | 문서·질문을 로컬에서 처리 가능 | 모델 다운로드·하드웨어·한국어 품질 검증 필요 |

현재 LangChain은 설치하지 않았어. RAG는 라이브러리 이름이 아니라
`문서 추출 → 청크 → 임베딩 검색 → 근거 기반 생성` 흐름이므로 공식 SDK만으로도 구현할 수 있어.
API 동작 설명은 설치한 openai 3.26.0과
[임베딩 문서](https://developers.openai.com/api/docs/guides/embeddings),
[gpt-5-mini 문서](https://developers.openai.com/api/docs/models/gpt-5-mini)를 기준으로 했어.

## 검증과 평가

```powershell
# 합성 PDF·가짜 API만 사용하는 전체 회귀 테스트. 키·원본 PDF·네트워크 불필요.
.venv/Scripts/python.exe -m pytest
# 로컬 원본에서 생성한 파싱 결과와 기대 근거/수치 보존 검사. API 호출 없음.
.venv/Scripts/python.exe -m avante_manual_rag.cli evaluate --cases evaluation/cases.cn7n-2025.json --mode local
# 유료 실제 API 평가. 상세는 data/processed/reports/<generation>/detail.json에만 저장.
.venv/Scripts/python.exe -m avante_manual_rag.cli evaluate --cases evaluation/cases.cn7n-2025.json --mode live
# 각 결과에 수동 의미 판정을 기록한 로컬 보고서로 최종 지표 계산.
.venv/Scripts/python.exe -m avante_manual_rag.cli evaluate --cases evaluation/cases.cn7n-2025.json --mode judge --report data/processed/reports/<generation>/detail.json
```

일반/표/사양/근거 부족 각 4개, 총 16개 사례가 있어. `required_bundles`의 **각 묶음마다 하나
이상**의 근거 블록이 top-5에 검색돼야 해당 답변 가능 사례의 검색 성공으로 세어.
이 프로젝트의 Recall@5는 성공 사례 수 / 답변 가능 사례 수야. 단순히 관련 문서 하나만
검색됐다고 성공으로 세지 않아. 근거 부족에 무조건 유보하는 모델도 답변 가능 질문에서 실패해.

상세 결과의 `judgment`는 처음에 null이야. 원문·주장·수치/단위·경고·인용 페이지를 사례의
criteria와 대조한 다음 `{ "pass": true, "scope_errors": 0, "citation_errors": 0,
"numeric_unit_errors": 0, "warning_errors": 0 }`와 별도 판정 메모를 기록해.
공유할 때는 원문과 발췌가 들어 있는 detail을 내보내지 말고 summary 또는 judge 출력만 사용해.
미판정/미실행은 통과가 아니야. 검색/답변 각 90% 이상, 해당 오류 0건,
근거 부족 전부 유보가 품질 기준이야. 이 16개는 작은 회귀 세트이며 전체 매뉴얼 정확도를
대표하는 통계적 보장이 아니야.

최신 실행 결과와 미검증 영역은 `docs/implementation-validation.md`에 기록해.
배포 확인은 `.venv/Scripts/python.exe -m build --no-isolation` 후 wheel/sdist 목록에서
PDF, `.env`, `data/`, 로컬 설정 포함 여부를 검사해. 패키지는 `src/avante_manual_rag`만 포함해.
