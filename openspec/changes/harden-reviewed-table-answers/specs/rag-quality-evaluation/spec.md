# Spec Delta

## MODIFIED Requirements

### Requirement: Measurable baseline acceptance

초기 인수는 승인된 표·다단·경고 파싱 사례의 필수 항목 보존, 답변 가능한 사례의 근거 검색
Recall@5 90% 이상, 답변 가능한 사례의 답변 통과율 90% 이상을 요구한다(SHALL).
사양 혼입·잘못된 인용·수치/단위/필수 경고 오류는 0건이어야 하고, 근거 부족 사례는 모두
안전하게 답변을 유보해야 한다(SHALL). 통과율의 분자·분모는 모두 답변 가능 사례로 제한하고
필수 파싱 검사나 의미 판정이 누락·실패한 실행을 전체 통과로 표시해서는 안 된다(MUST NOT).

#### Scenario: Assess a baseline run
- **WHEN** 16개 승인 사례를 고정된 설정으로 평가한다
- **THEN** 사례별 결과와 지표의 분자·분모를 보고하고 모든 기준을 만족한 경우에만 해당 실행을 통과로 표시한다
- **AND** 적용 조건 확인이 정답인 사례는 확인 요청의 적절성을 평가하며 답변 가능한 사례에서 무조건 유보하는 응답은 실패다

#### Scenario: Incomplete parsing coverage
- **WHEN** 대상 PDF의 전체 페이지 상태가 기록됐지만 일부 구간은 미처리 상태다
- **THEN** 미처리 목록을 함께 보고하고 평가에 사용한 근거가 미처리 구간에 의존하면 해당 사례를 통과시키지 않는다
- **AND** 대표 사례 통과를 전체 매뉴얼의 답변 정확성 보장으로 표현하지 않는다

#### Scenario: Correct denominator with non-answerable cases
- **WHEN** 답변 가능 10개 중 9개와 확인 요청·유보 6개가 모두 통과한다
- **THEN** 답변 통과율을 9/10으로 보고하고 확인 요청·유보의 결과는 별도로 보고한다

#### Scenario: Parsing failure in live or judged evaluation
- **WHEN** 필수 파싱 검사가 실패·미실행이거나 보고서에 빠진 상태로 실행 또는 재판정한다
- **THEN** 검색·답변 비율이 높아도 quality_gate를 통과시키지 않는다
- **AND** 답변 가능 사례가 없는 보고서의 비율은 미정으로 남기고 통과시키지 않는다

## ADDED Requirements

### Requirement: Default regressions for reviewed evidence

기본 자동 테스트는 표 관계·출처·조건·경고의 훼손과 리뷰에서 재현한 오류를 포함해야
한다(SHALL). 합성 입력으로 값 교환과 사실 참조 우회를 검증하며 실제 PDF나 유료 호출을
필수로 요구해서는 안 된다(MUST NOT).

#### Scenario: Run the configured suite
- **WHEN** 구성된 기본 회귀 명령을 실행한다
- **THEN** 기존 리뷰 재현 테스트도 자동 수집되고 앞뒤 값·오일 항목 혼동·잘못된 사실 ID·조건 및 경고 누락을 검사한다

#### Scenario: Separate rendering checks from selection quality
- **WHEN** 구조화된 수치 답변을 평가한다
- **THEN** 사실 자체의 원문 일치, 질문에 맞는 사실 선택, 문장 구성·인용 보존을 구분해 판정한다
- **AND** 정확한 값 출력만으로 무관한 사실 선택을 통과시키지 않는다

### Requirement: Durable partial evaluation and traceable judgments

실제 평가에서 완료한 사례와 확인된 사용량은 후속 사례의 서비스 실패로 유실되지 않도록
저장해야 한다(SHALL). 판정에는 검토자·유형·날짜와 근거를 기록하고 이전 기록의 재계산을
새 모델 실행으로 표시하거나 기존 불변 보고서를 덮어써서는 안 된다(MUST NOT).

#### Scenario: Provider error during a later case
- **WHEN** 일부 사례 완료 후 후속 사례에서 예상 가능한 SDK 오류가 발생한다
- **THEN** 완료 사례·확인된 사용량·실패 사례를 보존하고 나머지 사례를 계속 평가한다
- **AND** 미실행·미판정 사례를 성공으로 채우지 않으며 평가 실패는 CLI의 0이 아닌 종료 코드로 전달한다

#### Scenario: Recalculate a historical report
- **WHEN** 기존 사례별 판정으로 지표를 정정한다
- **THEN** API 재호출 없이 출처 보고서와 새 계산 버전을 기록한 별도 결과를 만든다
- **AND** 확인된 파싱 결과만 반영하고 과거 기록에 없는 검증이나 사람의 승인을 만들어내지 않는다
