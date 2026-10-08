# Spec Delta

## MODIFIED Requirements

### Requirement: Preserve numerical and safety conditions

시스템은 수치·단위·적용 조건과 관련 경고를 함께 제시하고 중요한 경고를 완화하거나
생략해서는 안 된다(MUST NOT). 조건별 값이 다른 경우 조건별로 답하거나 추가 조건을
확인해야 한다(SHALL). 표 기반 수치 주장은 검색된 승인 사실에서 대상·항목·조건·값·단위를
함께 구성해야 하며 모델이 작성한 수치 문장으로 대체해서는 안 된다(MUST NOT).

#### Scenario: Conditional tire pressure question
- **WHEN** 주행 조건을 지정하지 않은 공기압 질문에 여러 조건의 근거가 검색된다
- **THEN** 조건별 차이와 해당 각주를 보존하거나 필요한 조건을 되묻고 단일 값을 무조건 권장하지 않는다

#### Scenario: DCT fluid question
- **WHEN** DCT의 서로 다른 오일 항목이 근거에 포함된다
- **THEN** 항목명·수치·단위를 구분하고 관련 적용 조건과 주의를 연결하여 수동변속기 값과 혼동하지 않는다

#### Scenario: Swapped values in a model claim
- **WHEN** 모델이 합성 표의 앞 250 kPa와 뒤 235 kPa를 바꾼 자유 문장을 반환한다
- **THEN** 같은 표에 두 숫자가 있다는 이유로 통과시키지 않고 허용되지 않은 주장 형식으로 거부한다
- **AND** 정상 답변의 대상·값 조합은 선택된 승인 사실에서 구성한다

#### Scenario: Mixed narrative and table answer
- **WHEN** 일반 설명과 표 수치를 함께 답한다
- **THEN** 표 수치는 사실 참조로만 구성하고 설명 문장 경로로 재작성하는 결과는 거부한다

### Requirement: Preserve stored evidence when limiting context

시스템은 모델 입력 한도 때문에 근거를 줄여도 저장된 원본과 청크를 변경해서는 안 된다(MUST NOT).
필수 표 제목·각주·경고를 보존할 수 없는 근거는 부분 잘림 상태로 답변에 사용해서는 안 된다(MUST NOT).
발췌 후보 생성과 문맥 선택에서 제외된 근거의 식별자 및 이유를 보고해야 한다(SHALL).

#### Scenario: Evidence exceeds the input budget
- **WHEN** 선택한 근거와 필수 경고의 합계가 모델 입력 예산을 넘는다
- **THEN** 완전한 근거 묶음 단위로 수를 줄이고 충분한 근거를 담을 수 없으면 그 한계를 응답한다
- **AND** 모든 근거가 제외되면 모델 호출 없이 insufficient_evidence와 context_budget 사유를 반환한다

#### Scenario: Long evidence and late warnings
- **WHEN** 짧은 문장 뒤에 긴 표가 있거나 청크 후반에 필수 경고가 있다
- **THEN** 앞부분 후보만으로 조용히 자르지 않고 필요한 사실·발췌·경고를 제공하거나 제외 이유를 보고한다

## ADDED Requirements

### Requirement: Grounded fact selection and rendering

시스템은 이번 요청에 제공된 승인 사실 ID만 선택하도록 제한하고 ID와 근거·출처·조건·
필수 경고의 일치를 검증해야 한다(SHALL). 검증된 사실에서 문장과 인용을 구성하고 모델이
작성한 대상·값·페이지로 덮어써서는 안 된다(MUST NOT).

#### Scenario: Unknown or mismatched fact identifier
- **WHEN** 모델이 미제공 사실이나 다른 근거에 속한 사실 ID를 선택한다
- **THEN** 인용 검증 실패로 반환하고 정상 답변을 출력하지 않는다

#### Scenario: Unstructured or incomplete table evidence
- **WHEN** 표는 검색됐지만 승인 사실 관계 또는 필수 경고가 없다
- **THEN** 해당 표로 수치 답변을 생성하지 않고 검토 부족을 알리며 답에 필요한 근거가 없으면 유보한다

#### Scenario: Conflicting facts
- **WHEN** 동일 대상·항목·적용 조건에 서로 다른 값의 승인 사실이 제공된다
- **THEN** 하나를 임의 선택하지 않고 conflicting_evidence를 반환한다
- **AND** 조건이 다른 값은 조건별 차이로 구분한다

### Requirement: Preflight before paid retrieval

시스템은 답변 요청의 입력·생성 설정과 명시적인 차량 사양 충돌을 유료 검색 전에 검사해야
한다(SHALL). 보증 연도나 DCT 수동 모드를 연식·변속기 충돌로 단정해서는 안 된다(MUST NOT).
검색 전용 요청에는 생성 모델 설정을 요구해서는 안 된다(MUST NOT).

#### Scenario: Missing generation configuration
- **WHEN** 생성 모델 설정이 없는 상태로 답변을 요청한다
- **THEN** 질문 임베딩·생성 호출 없이 설정 오류와 0이 아닌 종료 코드를 반환한다

#### Scenario: Explicit incompatible vehicle
- **WHEN** 질문이 지원 차량과 다른 연식 또는 수동변속기 차량을 명시한다
- **THEN** 검색 호출 없이 needs_clarification을 반환한다

#### Scenario: Supported operating mode or unrelated year
- **WHEN** 질문에 2030년까지의 보증이나 DCT의 수동 모드가 언급된다
- **THEN** 그 표현만으로 사양 충돌을 반환하지 않고 정상 근거 검색 및 부족 판정을 진행한다

### Requirement: Bounded provider failure handling

시스템은 외부 호출 경계에서 SDK의 응답 검증 오류를 포함한 예상 가능한 서비스 오류를
처리 단계별 장애로 변환해야 한다(SHALL). 인증·잘못된 응답을 무한 재시도하거나 근거
부족으로 숨겨서는 안 된다(MUST NOT). 내부 프로그래밍 오류를 무조건 잡아 숨겨서도 안 된다(MUST NOT).

#### Scenario: Provider response validation error
- **WHEN** 외부 SDK가 응답 검증 예외를 반환한다
- **THEN** 해당 검색 또는 생성 장애로 기록하고 일반 CLI 출력에 traceback이나 비밀값을 노출하지 않는다
- **AND** 잘못된 응답은 재시도하지 않고 CLI는 0이 아닌 종료 코드를 반환한다
