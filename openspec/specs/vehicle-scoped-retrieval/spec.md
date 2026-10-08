# vehicle-scoped-retrieval Specification

## Purpose

질문에 관련된 매뉴얼 근거를 차량과 변속기의 적용 범위 안에서 검색한다. 청크가 원문의
표·경고·적용 조건과 연결되도록 하고, 재생성된 색인과 모델의 호환성을 추적한다.

## Requirements

### Requirement: Evidence units retain structural context

시스템은 청크마다 원본 문서·페이지·절·적용 범위와 근거 블록을 연결해야 한다(SHALL).
표를 나눌 때 필요한 열 제목, 단위, 각주와 경고를 각 결과에 복원할 수 있어야 하며,
검토가 끝나지 않은 구조를 검증된 근거로 색인해서는 안 된다(MUST NOT).

#### Scenario: Search a table row
- **WHEN** DCT 관련 표 행이 검색된다
- **THEN** 결과에는 항목명과 값뿐 아니라 단위, 열 제목, 해당 각주·경고 및 원본 페이지가 연결된다

#### Scenario: Keep warnings with procedures
- **WHEN** 주의 또는 경고가 연결된 절차 청크를 검색한다
- **THEN** 절차에 필요한 경고가 근거 묶음에 포함되며 무관한 절의 경고와 섞이지 않는다

### Requirement: Filter vehicle applicability before ranking

시스템은 질문과 함께 받은 차량 조건을 검색 후보 선정에 적용해야 한다(SHALL).
최초 지원 프로필 CN7N/2025/DCT에서는 해당 문서의 DCT 전용 및 확인된 공통 근거만 답변 후보로
허용하고 다른 차량·연식·수동 전용 근거를 제외해야 한다(SHALL).

#### Scenario: More similar but incompatible evidence
- **WHEN** 다른 연식 또는 수동 전용 청크가 질문과 더 높은 유사도를 가진다
- **THEN** 해당 청크는 DCT 답변 후보에 포함되지 않는다

#### Scenario: Mixed transmission table
- **WHEN** 한 표에 공통 제목·각주와 수동·DCT 행이 함께 있다
- **THEN** DCT 행과 필요한 공통 맥락을 선택하고 수동 전용 값을 DCT의 값으로 반환하지 않는다

### Requirement: Unresolved applicability is explicit

시스템은 적용 미확인을 공통 적용으로 간주해서는 안 된다(MUST NOT).
변속기 외의 옵션·주행 조건에 따라 답이 달라지면 조건을 보존하고 추가 확인 필요를 표시해야 한다(SHALL).

#### Scenario: Unknown transmission classification
- **WHEN** 관련 청크의 변속기 적용 범위를 확인하지 못했다
- **THEN** 해당 청크를 확정 답변 근거에서 제외하고 적용 범위 검토 필요 사유를 반환한다

#### Scenario: Question lacks an operating condition
- **WHEN** 질문의 답이 일반·고속·트랙 주행 조건에 따라 달라진다
- **THEN** 결과는 각 조건을 유지하며 하나의 값을 무조건 적용 가능한 답으로 취급하지 않는다

### Requirement: Compatible and repeatable indexes

시스템은 원본·파싱·청크 설정 및 임베딩 제공자·모델 ID·차원·전처리 버전을 색인에 기록하고,
질의 설정과 호환되지 않는 색인의 검색을 거부해야 한다(SHALL). 공개된 리비전은 함께 기록하되
제공되지 않는 모델 해시를 만들어서는 안 된다(MUST NOT). 재실행은 중복을 방지하고 재색인 실패 시
기존 활성 색인과 근거 매핑을 보존해야 한다(SHALL).

#### Scenario: Model or configuration changes
- **WHEN** 제공자·모델 ID·공개된 리비전·차원·전처리 중 하나가 색인과 다르거나 파싱·청크 설정이 변경됐다
- **THEN** 재생성이 필요한 범위를 보고하고 호환되지 않는 데이터를 함께 검색하지 않는다

#### Scenario: Repeat and interrupt indexing
- **WHEN** 같은 입력을 재색인하거나 새 색인 생성 도중 중단된다
- **THEN** 전자는 활성 청크 수를 불필요하게 늘리지 않고 후자는 기존 정상 색인을 계속 사용하게 한다

#### Scenario: Index and evidence metadata do not match
- **WHEN** 저장된 벡터 색인과 문서·페이지 매핑의 데이터 세대, 항목 수 또는 무결성 정보가 일치하지 않는다
- **THEN** 검색을 거부하고 다른 청크의 페이지를 인용하는 결과를 반환하지 않는다

### Requirement: Inspectable retrieval results

시스템은 CLI에서 답변 생성 없이 상위 근거, 출처, 적용 조건 및 처리 누락 상태를 조회할 수
있어야 한다(SHALL). 검색 점수는 순위용 값으로만 표시하고 정확도 확률로 설명해서는 안 된다(MUST NOT).

#### Scenario: Search without a generation model
- **WHEN** 임베딩 검색이 가능한 환경에서 사용자가 검색만 요청한다
- **THEN** 생성 모델을 호출하지 않고 근거와 페이지를 반환한다

#### Scenario: Distinguish empty results and search errors
- **WHEN** 호환 후보가 없거나 임베딩 호출·색인 읽기에 실패한다
- **THEN** 전자는 근거 부족으로, 후자는 검색 장애로 구분하며 장애 시 CLI는 0이 아닌 종료 코드를 반환한다
