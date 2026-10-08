# Spec Delta

## ADDED Requirements

### Requirement: Recorded manual analysis before rule changes

프로젝트는 파싱·청크 규칙을 구현하거나 변경하기 전에 대표 원문을 시각적으로 분석하고
판단 근거를 기록해야 한다(SHALL). 기록은 원본 해시·차량 범위·검토 위치·좌표계·검토자·
유형·날짜·미확인 영역을 포함해야 하며 대표 분석을 전체 문서 검토로 표시해서는 안 된다(MUST NOT).

#### Scenario: Analyze representative layouts
- **WHEN** 표·다단·경고·혼합 사양을 처리하는 규칙 변경을 시작한다
- **THEN** 대표 페이지에서 읽기 순서, 머리글/값/단위/각주 관계, 경고 적용 범위와 필수 연결을 기록한다
- **AND** 그림·빈 추출·스캔 유형의 확인 여부와 미확인 사항을 기록하고 그 결과로 처리 규칙을 정한다

#### Scenario: Reuse a previous analysis
- **WHEN** 기존 분석이나 좌표 보정을 재사용한다
- **THEN** 원본 해시와 페이지·좌표계·적용 범위를 대조하고 원본 또는 규칙 변경의 영향 구간을 재검토한다
- **AND** 에이전트 검토를 사람의 검토나 실행 프로그램의 자동 의미 분석으로 표시하지 않는다

### Requirement: Source comparison before evidence approval

프로젝트는 파싱·청크 변경 후 사전 분석한 동일 원문과 실제 페이지·블록·청크 결과를 대조하고
관계·조건·경고·출처 보존 결과를 기록해야 한다(SHALL). 대조하지 않았거나 필요한 관계가
불명확한 근거는 검증된 답변용 근거로 승인해서는 안 된다(MUST NOT).

#### Scenario: Compare generated evidence with the source
- **WHEN** 분석한 페이지를 새 규칙으로 처리한다
- **THEN** 대상별 수치·단위, 필수 조건·경고, PDF/인쇄 페이지 대응과 누락을 대조한다
- **AND** 실패 영역은 미검증으로 유지하며 수정 후 같은 원문으로 다시 대조한다

#### Scenario: Store review evidence privately
- **WHEN** 원문 렌더링·발췌·검토 결과를 저장한다
- **THEN** 상세 자료는 로컬 제외 경로에 보관하고 공유 문서에는 처리 규칙·근거 위치·한계만 남긴다

### Requirement: Reviewed structured table facts

시스템은 승인된 표 수치마다 대상·항목·조건·차량 범위·값·단위와 필수 각주/경고를 결합한
식별 가능한 사실을 보존해야 한다(SHALL). 사실은 원본 해시, PDF/인쇄 페이지, 표 위치 및
검토 기록으로 추적 가능해야 하며 추출된 셀만으로 관계를 승인해서는 안 된다(MUST NOT).

#### Scenario: Preserve a conditional measurement
- **WHEN** 여러 주행 조건과 앞뒤 위치가 있는 표를 승인한다
- **THEN** 각 사실에 조건·위치·값·단위와 적용 각주가 연결되고 범위·상하한·복수 단위 표현도 보존된다
- **AND** 일부 인쇄 번호를 확인하지 못했어도 해당 PDF 페이지와 미확인 번호의 대응은 유지된다

#### Scenario: Reject incomplete or stale fact records
- **WHEN** 사실의 원본 해시가 다르거나 출처·필수 연결·검토 이력이 누락됐다
- **THEN** 계약 오류 또는 검토 필요를 명시하고 검증된 표 사실로 사용하지 않는다
- **AND** 기존 정상 산출물과 원본을 변경하지 않는다

#### Scenario: Distinguish fact review from extraction
- **WHEN** 자동 추출 결과에 표가 있지만 승인된 사실 관계가 없다
- **THEN** 추출 결과는 보존하되 해당 표를 수치 답변용으로 승인하지 않는다
