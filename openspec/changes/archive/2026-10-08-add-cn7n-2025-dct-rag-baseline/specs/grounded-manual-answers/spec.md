# Spec Delta

## Purpose

사용자의 차량에 적용되는 검색 근거를 바탕으로 한국어 답변과 추적 가능한 인용을 제공한다.
모르는 내용과 실행 장애를 구분하고, 매뉴얼의 수치·조건·경고를 손상하지 않는 답변을 평가한다.

## ADDED Requirements

### Requirement: Retrieve before generating an answer

시스템은 차량 조건으로 검색한 근거를 답변 생성에 제공하고 한국어로 응답해야 한다(SHALL).
매뉴얼의 설명과 모델의 추론을 구분해야 하며 차량 관련 사실을 모델 기억만으로 보완해서는
안 된다(MUST NOT).

#### Scenario: Answer a supported question
- **WHEN** CN7N/2025/DCT 질문에 충분한 적용 가능 근거가 검색된다
- **THEN** 시스템은 해당 근거를 사용해 답변하고 다른 사양의 설명을 섞지 않는다

#### Scenario: Prompt injection inside a manual
- **WHEN** 검색한 본문에 개발 지시를 무시하거나 임의 명령을 실행하라는 문장이 있다
- **THEN** 이를 참고 데이터로만 취급하고 명령을 실행하거나 답변 규칙을 변경하지 않는다

### Requirement: Validate and display actual citations

시스템은 답변의 매뉴얼 관련 주장에 실제 검색 결과의 근거를 연결하고 문서명, PDF 페이지,
확인된 인쇄 페이지 또는 절을 표시해야 한다(SHALL). 존재하지 않는 근거 ID·페이지·발췌문을
포함한 생성 결과는 정상 답변으로 표시해서는 안 된다(MUST NOT).

#### Scenario: Valid evidence references
- **WHEN** 모델이 검색 결과에 포함된 근거를 인용한다
- **THEN** 시스템은 저장된 메타데이터로 인용을 구성하고 해당 원본 페이지를 확인할 수 있게 한다

#### Scenario: Fabricated citation or unsupported claim
- **WHEN** 인용 ID가 없거나 발췌문이 원문에 없거나 평가에서 주장이 인용 근거로 뒷받침되지 않는다
- **THEN** 자동 검사에서 발견된 인용 오류는 검증 실패로 반환하고, 의미 불일치는 답변 품질 평가 실패로 기록한다
- **AND** 인용의 형식 검사를 통과했다는 이유로 의미적 정확성이 보장됐다고 표시하지 않는다

### Requirement: Preserve numerical and safety conditions

시스템은 수치·단위·적용 조건과 관련 경고를 함께 제시하고 중요한 경고를 완화하거나
생략해서는 안 된다(MUST NOT). 조건별 값이 다른 경우 조건별로 답하거나 추가 조건을
확인해야 한다(SHALL).

#### Scenario: Conditional tire pressure question
- **WHEN** 주행 조건을 지정하지 않은 공기압 질문에 여러 조건의 근거가 검색된다
- **THEN** 조건별 차이와 해당 각주를 보존하거나 필요한 조건을 되묻고 단일 값을 무조건 권장하지 않는다

#### Scenario: DCT fluid question
- **WHEN** DCT의 서로 다른 오일 항목이 근거에 포함된다
- **THEN** 항목명·수치·단위를 구분하고 관련 적용 조건과 주의를 연결하여 수동변속기 값과 혼동하지 않는다

### Requirement: Honest absence and failure responses

시스템은 근거 부족, 사양 확인 필요, 근거 상충, 검색 장애, 모델 장애, 인용 검증 실패를
구분해야 한다(SHALL). 처리되지 않은 페이지가 있는 상태에서 검색 실패를 매뉴얼 전체에
답이 없다는 사실로 단정해서는 안 된다(MUST NOT).

#### Scenario: Missing or conflicting evidence
- **WHEN** 답을 뒷받침할 근거가 없거나 적용 가능한 근거끼리 충돌한다
- **THEN** 시스템은 부족 또는 상충 상태와 처리 범위를 알리고 임의의 결론을 생성하지 않는다

#### Scenario: Backend timeout or invalid response
- **WHEN** 검색 또는 생성 서비스가 시간 초과·연결 실패·잘못된 응답을 반환한다
- **THEN** 서비스 장애를 표시하고 CLI는 0이 아닌 종료 코드를 반환하며 근거 부족 메시지로 바꾸지 않는다

### Requirement: Preserve stored evidence when limiting context

시스템은 모델 입력 한도 때문에 근거를 줄여도 저장된 원본과 청크를 변경해서는 안 된다(MUST NOT).
필수 표 제목·각주·경고를 보존할 수 없는 근거는 부분 잘림 상태로 답변에 사용해서는 안 된다(MUST NOT).

#### Scenario: Evidence exceeds the input budget
- **WHEN** 선택한 근거와 필수 경고의 합계가 모델 입력 예산을 넘는다
- **THEN** 완전한 근거 묶음 단위로 수를 줄이고 충분한 근거를 담을 수 없으면 그 한계를 응답한다

### Requirement: API execution and limited data exposure

초기 시스템은 OpenAI API로 임베딩·생성을 실행하고 키를 환경변수에서 읽어야 한다(SHALL).
임베딩에는 청크·질문을, 생성에는 질문·차량 조건·선택 근거를 전송하며 원본 PDF 파일을
업로드하거나 배포해서는 안 된다(MUST NOT). 기본 로그에 질문·문서 전문·인증 정보를
남겨서는 안 된다(MUST NOT).

#### Scenario: Run with configured API access
- **WHEN** OpenAI API 키와 접근 가능한 생성 모델 및 매뉴얼이 준비된 환경에서 질의한다
- **THEN** 로컬 모델 서버 없이 답변을 생성하고 사용 모델과 토큰 사용량을 기록한다
- **AND** 필요한 텍스트만 전송하고 PDF 바이너리나 키를 출력에 포함하지 않는다

#### Scenario: Missing key or authentication failure
- **WHEN** 실제 API 호출에 필요한 키가 없거나 인증·모델 접근 권한이 거부된다
- **THEN** 설정 또는 API 접근 오류와 0이 아닌 종료 코드를 반환하며 근거 부족으로 바꾸거나 무한 재시도하지 않는다

#### Scenario: Capture an error log
- **WHEN** 모델 호출 또는 인용 검사에서 실패한다
- **THEN** 로그로 단계를 식별할 수 있지만 질문 전문·매뉴얼 전문·비밀값은 기본 출력에 포함되지 않는다
