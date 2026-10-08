# Spec Delta

## MODIFIED Requirements

### Requirement: Evidence units retain structural context

시스템은 청크마다 원본 문서·페이지·절·적용 범위와 근거 블록을 연결해야 한다(SHALL).
표를 나눌 때 필요한 열 제목, 단위, 각주와 경고를 각 결과에 복원할 수 있어야 하며,
검토가 끝나지 않은 구조를 검증된 근거로 색인해서는 안 된다(MUST NOT).
승인된 표 사실의 식별자와 관계를 검색 결과까지 보존하고 PDF 페이지별 인쇄 번호 또는
미확인 상태를 명시적으로 대응시켜야 한다(SHALL).

#### Scenario: Search a table row
- **WHEN** DCT 관련 표 행이 검색된다
- **THEN** 결과에는 항목명과 값뿐 아니라 단위, 열 제목, 해당 각주·경고 및 원본 페이지가 연결된다
- **AND** 승인된 사실의 대상·조건·값 연결이 답변 단계까지 유지된다

#### Scenario: Keep warnings with procedures
- **WHEN** 주의 또는 경고가 연결된 절차 청크를 검색한다
- **THEN** 절차에 필요한 경고가 근거 묶음에 포함되며 무관한 절의 경고와 섞이지 않는다

#### Scenario: Mixed known and unknown printed pages
- **WHEN** 여러 PDF 페이지를 묶고 일부 인쇄 번호만 확인됐다
- **THEN** 각 PDF 페이지에 해당 인쇄 번호 또는 미확인을 대응시키며 목록 압축으로 위치를 바꾸지 않는다

## ADDED Requirements

### Requirement: Required and optional evidence links

시스템은 근거의 필수 맥락과 선택적 관련 근거를 구분해야 한다(SHALL). 다른 사양의 선택
근거는 제외하되 필수 연결이 미검토·부적합이면 해당 묶음을 미검증으로 제외하고 이유를
보고해야 한다(SHALL). 이 때문에 독립적인 정상 근거의 색인 전체를 중단해서는 안 된다(MUST NOT).

#### Scenario: Optional manual transmission row
- **WHEN** DCT 표 묶음이 수동 전용 행을 선택적 관련 근거로 참조한다
- **THEN** 수동 행을 제외하고 검토된 DCT 행과 필요한 공통 맥락으로 색인한다

#### Scenario: Unreviewed required warning
- **WHEN** DCT 근거의 필수 경고가 미검토이거나 적용 범위가 불명확하다
- **THEN** 해당 묶음을 제외하고 근거 ID·필수 연결·사유를 보고하며 독립적인 정상 묶음은 처리한다

#### Scenario: Broken link contract
- **WHEN** 연결이 존재하지 않는 블록을 참조하거나 식별자가 중복된다
- **THEN** 명시적인 계약 오류로 처리하고 이전 정상 색인을 보존한다
- **AND** 손상된 참조를 선택 근거 제외와 같은 정상 처리로 숨기지 않는다

### Requirement: Evidence contract compatibility

시스템은 표 사실·페이지 대응·검토 계약의 버전과 생성 이력을 색인에 기록하고 호환되지
않는 기존 산출물은 재생성 필요로 거부해야 한다(SHALL). 과거의 검토 완료 표시를 새로운
사실 관계의 검토 완료로 자동 승격해서는 안 된다(MUST NOT).

#### Scenario: Load an older evidence generation
- **WHEN** 검색이 구버전 페이지·청크·사실 계약으로 만든 색인을 읽는다
- **THEN** 계약 불일치를 알리고 검토 자료 보완·재파싱·재색인이 필요한 범위를 안내한다

#### Scenario: Change structured facts without changing source text
- **WHEN** 원문은 같지만 사실 관계 또는 검토 설정이 바뀐다
- **THEN** 기존 사실 ID·출처 매핑을 새 결과에 섞지 않고 새 데이터 세대와 호환되는 결과만 검색한다
