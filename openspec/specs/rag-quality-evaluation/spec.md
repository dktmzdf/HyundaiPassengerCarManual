# rag-quality-evaluation Specification

## Purpose

파싱, 검색, 답변의 품질을 분리해 초기 매뉴얼 RAG가 어디서 실패하는지 확인한다.
재현 가능한 질문과 원문 근거, 자동 검사 및 실제 모델 평가 기록으로 구현 완료를 판단한다.

## Requirements

### Requirement: Versioned representative evaluation cases

프로젝트는 일반 기능, 표 기반 수치, 적용 사양, 근거 부족의 네 범주에서 각각 4개씩 총 16개의
대표 질문을 관리해야 한다(SHALL). 각 사례에는 차량 조건, 기대 응답 상태, 원문에서 확인한
근거 페이지·절 또는 근거 없음의 판단 범위, 필수 조건과 판정 기준을 기록해야 한다(SHALL).

#### Scenario: Add a table evaluation case
- **WHEN** 타이어 또는 DCT 오일 관련 평가 사례를 등록한다
- **THEN** 원문에서 검토한 행·열·단위·각주와 PDF/인쇄 페이지를 기대 근거로 연결한다
- **AND** 아직 원문을 확인하지 않았다면 검토 대기로 남겨 승인된 평가 사례로 계산하지 않는다

#### Scenario: Define a no-evidence case
- **WHEN** 매뉴얼 근거가 없는 질문을 등록한다
- **THEN** 무엇을 확인했고 어떤 응답을 기대하는지 기록하며 외부 지식으로 답하도록 요구하지 않는다

### Requirement: Separate parsing retrieval and answer metrics

평가는 페이지 처리 현황과 구조 보존, 정답 근거 검색, 답변의 근거 일치·수치·조건·인용을
서로 다른 결과로 보고해야 한다(SHALL). 실행 성공이나 답변 문자열의 완전 일치만으로 품질을
판정해서는 안 된다(MUST NOT).

#### Scenario: Isolate a retrieval failure
- **WHEN** 원문 근거는 올바르게 파싱됐지만 상위 검색 결과에 나오지 않는다
- **THEN** 검색 실패로 분류하고 생성 모델의 실패와 구분한다

#### Scenario: Isolate a generation failure
- **WHEN** 필요한 근거가 모델에 전달됐지만 답변이 수치·조건을 바꾸거나 잘못 인용한다
- **THEN** 답변 품질 실패로 기록하고 검색 성공만으로 전체 사례를 통과시키지 않는다

### Requirement: Offline regression tests and explicit live evaluation

기본 자동 테스트는 합성 입력과 임시 저장소 및 모의 모델로 네트워크·실제 모델·유료 API 키 없이
실행돼야 한다(SHALL). 원본을 사용하는 로컬 통합 평가와 실제 모델 평가는 별도 실행으로 구분하고
미실행·실패·통과를 명시해야 한다(SHALL).

#### Scenario: Run tests in an isolated environment
- **WHEN** 실제 PDF나 OpenAI API 키가 없는 개발 환경에서 기본 테스트를 실행한다
- **THEN** 기본 테스트를 실행할 수 있고 외부 호출과 원본 파일 변경이 발생하지 않는다

#### Scenario: Live model is unavailable
- **WHEN** 실제 모델 평가를 요청했지만 키·모델 접근 권한·할당량·네트워크가 준비되지 않았다
- **THEN** 설정 문제 또는 미실행으로 보고하고 모의 테스트 결과로 실제 답변 품질을 대체하지 않는다

### Requirement: Measurable baseline acceptance

초기 인수는 승인된 표·다단·경고 파싱 사례의 필수 항목 보존, 답변 가능한 사례의 근거 검색
Recall@5 90% 이상, 답변 가능한 사례의 답변 통과율 90% 이상을 요구한다(SHALL).
사양 혼입·잘못된 인용·수치/단위/필수 경고 오류는 0건이어야 하고, 근거 부족 사례는 모두
안전하게 답변을 유보해야 한다(SHALL).

#### Scenario: Assess a baseline run
- **WHEN** 16개 승인 사례를 고정된 설정으로 평가한다
- **THEN** 사례별 결과와 지표의 분자·분모를 보고하고 모든 기준을 만족한 경우에만 해당 실행을 통과로 표시한다
- **AND** 적용 조건 확인이 정답인 사례는 확인 요청의 적절성을 평가하며 답변 가능한 사례에서 무조건 유보하는 응답은 실패다

#### Scenario: Incomplete parsing coverage
- **WHEN** 대상 PDF의 전체 페이지 상태가 기록됐지만 일부 구간은 미처리 상태다
- **THEN** 미처리 목록을 함께 보고하고 평가에 사용한 근거가 미처리 구간에 의존하면 해당 사례를 통과시키지 않는다
- **AND** 대표 사례 통과를 전체 매뉴얼의 답변 정확성 보장으로 표현하지 않는다

### Requirement: Reproducible and private evaluation reports

평가 기록에는 사례 버전, 원본 해시, 파서·청크·임베딩·생성 모델과 실행 설정, API 사용량, 실행 명령,
결과·미검증 범위를 남겨야 한다(SHALL). 원본 PDF와 개인 대화는 배포하지 않고, 모델 평가의
상세 근거·응답 파일은 로컬 데이터로 관리해야 한다(SHALL).

#### Scenario: Reproduce or share a result
- **WHEN** 평가 결과를 다시 실행하거나 요약을 공유한다
- **THEN** 요청·응답 모델 ID와 공개된 버전 정보, 데이터 세대를 식별할 수 있고 공유 자료에는 원본 PDF·API 키·개인 질문 로그가 없다
