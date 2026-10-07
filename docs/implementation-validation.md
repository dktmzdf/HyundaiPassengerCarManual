# 구현 및 검증 기록

`add-cn7n-2025-dct-rag-baseline`의 실행 결과야. 아래 품질 수치는 원문과 렌더링을 대조한
Codex 에이전트 판정이며, 독립된 사람의 검토나 전체 매뉴얼 정확도 보장은 아니야.

## 구현 결과

- Python CLI에서 등록 → 파싱 → 청크 → OpenAI 임베딩 → FAISS 검색 → gpt-5-mini 인용 답변을 연결했어.
- `.env` 또는 환경변수에서 키를 읽어. 키·인증 헤더는 출력하지 않아.
- 생성은 Responses, `store=false`, strict 출력과 `reasoning.effort=low`를 사용해.
  외부 응답의 `quote_id`를 검증해서 원문 발췌로 변환하므로 모델이 인용 문장을 다시 쓰지 않아.
- 검색은 CN7N/2025/DCT의 검토된 common/dct 청크만 포함해. FAISS IndexFlatIP/1536과
  float32 L2 정규화를 사용하고, 점수를 정답 확률로 해석하지 않아.
- JSON 메타데이터, 파일 해시 검증, 새 세대 생성과 활성 포인터 교체, 이전 세대 복귀를 구현했어.
  신뢰하지 않는 pickle은 사용하지 않아.

## 실행 환경

Windows / Python 3.11.9, pdfplumber 0.11.10, openai 3.26.0, faiss-cpu 1.15.1,
numpy 2.4.6, tiktoken 0.14.0, pytest 9.1.1, reportlab 5.0.1을 사용했어.
설치 버전은 `requirements.lock`에 고정했고, 프로젝트 `.venv`에서 실행했어.
다른 Python 버전과 OS는 검증하지 않았어.

## 원본 및 파싱

대표 PDF는 CN7N_2025_ko_KR.pdf, 16,757,322바이트, 436페이지야.
원본 SHA-256은 `87bbeec00684414edc31658bd0e104d714b35dab8fa8a46f68c35715a740bb0a`이며
manifest와 일치하고 처리 후에도 같아. 공식 출처 주소는 이번 접근 확인에서 열리지 않아
미검증으로 남겼고, 인용 링크를 생성하지 않아.

전체 페이지 처리 결과는 다음과 같아. `success`는 지정된 영역의 검토 완료를 뜻해.
부분 검토 페이지의 나머지 내용까지 검증했다는 뜻은 아니야.

| 상태 | 페이지 수 |
| --- | ---: |
| 검토 영역 있음 (`success`) | 6 |
| 검토 필요 (`needs_review`) | 424 |
| 빈 추출, OCR/시각 확인 필요 (`needs_ocr`) | 5 |
| 시각 확인한 빈 페이지 (`blank`) | 1 |
| 처리 실패/미처리 | 0 |

PDF 13/1-7의 타이어 표, 16/1-10의 혼합 오일 표를 렌더링과 대조했어.
205/6-13, 207/6-15, 208/6-16, 212/6-20의 DCT 본문과 경고는 열별 영역으로 검토했어.
PDF 6은 시각적으로 빈 페이지를 확인했고, PDF 200의 다단·그림 의존 내용은 검토 필요로 남겼어.
검토·영역 보정·출처 접근 기록은 배포 제외된 `data/reviews/`에 있어.
현재 활성 색인은 검토된 13개 청크야. 전체 매뉴얼의 모든 내용을 검색할 수 있는 상태는 아니야.

## 실제 API 평가

최종 실제 평가 세대는 `b21296a18fa24de9b21a721dbbe4be8b`야.
원본 API 보고서는 불변 세대에 보존했고, 판정은 `data/evaluation/judged-final.json` 복사본에 기록했어.
공유 가능한 집계는 [evaluation-summary.json](evaluation-summary.json)에 있어.

| 기준 | 최종 결과 |
| --- | ---: |
| 파싱 기대 근거·수치 보존 | 10/10 (나머지 6개는 비적용) |
| 필수 근거 Recall@5 | 9/10 (90%) |
| 답변 판정 | 15/16 (93.75%) |
| 다른 사양에 DCT 수치를 적용한 오류 | 0 |
| 인용/수치·단위/적용되는 필수 경고 오류 | 0 |
| 근거 부족 질문 유보 | 4/4 |
| 정의된 품질 기준 | 통과 |

`scope-2`는 기대한 직접 근거 PDF 205가 top-5에 없어서 근거 완전성 기준의 실패로 기록했어.
반환된 D/R 크리프 설명은 PDF 208/212로 뒷받침됐고 적용되는 브레이크 경고는 보존됐어.
이 실패를 검색 성공이나 완전한 답변 성공으로 바꾸지 않았어.

임베딩 요청/응답 모델은 text-embedding-3-small, 생성 요청 모델은 gpt-5-mini,
실제 생성 응답 모델은 gpt-5-mini-2025-08-07이었어.
현재 청크 색인 생성에서 새 임베딩 입력은 4,688토큰이었고 이후 재실행은 캐시를 재사용했어.
최종 16개 사례 실행은 14개 생성 호출, 입력 131,465토큰, 출력 5,667토큰이었어.
다른 사양 2개는 코드에서 사양 확인으로 분기했고 질문 임베딩은 기존 캐시를 재사용했어.
최대 개별 생성 입력은 10,702토큰이었어. 이는 최종 실행의 사용량이며 이전 수정·재평가 비용은 별도야.
금액은 실행 시점의 공식 모델 단가와 실제 청구 내역으로 확인해야 해.

초기 API 인증 오류와 부정확한 인용 발췌는 정상 답변으로 숨기지 않고 실패로 기록했어.
원문 발췌를 구조화 스키마에 반복하는 초기 방식은 입력 토큰이 늘어나는 문제가 있어
현재는 발췌 ID만 스키마에 넣고 본문을 참고 데이터로 보내.

## 검증 명령

다음 명령을 프로젝트 가상환경에서 실행했어.

```powershell
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m avante_manual_rag.cli --help
.venv/Scripts/python.exe -m avante_manual_rag.cli ingest --pages 6,13,16,200,205,207-208,212
.venv/Scripts/python.exe -m avante_manual_rag.cli ingest
.venv/Scripts/python.exe -m avante_manual_rag.cli index
.venv/Scripts/python.exe -m avante_manual_rag.cli search "DCT 기어오일의 용량과 추천 사양은?"
.venv/Scripts/python.exe -m avante_manual_rag.cli ask "DCT 기어오일의 용량과 추천 사양은?"
.venv/Scripts/python.exe -m avante_manual_rag.cli evaluate --cases evaluation/cases.cn7n-2025.json --mode local
.venv/Scripts/python.exe -m avante_manual_rag.cli evaluate --cases evaluation/cases.cn7n-2025.json --mode live
.venv/Scripts/python.exe -m avante_manual_rag.cli evaluate --cases evaluation/cases.cn7n-2025.json --mode judge --report data/evaluation/judged-final.json
.venv/Scripts/python.exe -m build --no-isolation
openspec validate add-cn7n-2025-dct-rag-baseline --strict
```

전체 기본 회귀는 **55개 통과**야. 합성 PDF·가짜 API·임시 디렉터리를 사용하고 네트워크를 차단해.
경로/디렉터리 링크 탈출, 페이지 오류·빈 추출·한글·다단·표, 혼합 변속기와 연결 경고,
벡터·캐시·응답 순서·재시도·인증/할당량·거부/불완전 응답, 인용 변조 및 유보를 검사했어.
재실행·중간 저장/재색인 실패·세대 복귀에서 원본과 정상 활성 결과가 보존되는 것도 확인했어.
wheel/sdist 목록에서 PDF, data/, .env, 로컬 설정이 포함되지 않는지 확인했어.

OCR, 그림 해석, 나머지 영역의 적용 범위 검토, 134권 전체 처리, 독립된 사람의 답변 평가는
아직 하지 않았어. 16개 회귀 세트 통과를 전체 매뉴얼의 정답률로 일반화하지 마.
