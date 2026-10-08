# Spec Delta

## Purpose

차량 매뉴얼 원본을 손상 없이 등록하고, 검색과 답변에 사용하는 내용이 어느 문서와 페이지에서
나왔는지 추적한다. 추출하지 못한 정보와 재처리 이력을 드러내어 데이터 품질을 판단할 수 있게 한다.

## ADDED Requirements

### Requirement: Verified local manual registration

시스템은 지정한 로컬 매뉴얼의 실제 크기와 SHA-256을 manifest와 대조하고 문서 식별자,
차종 코드, 연식, 언어, 출처 및 출처 검증 상태를 등록해야 한다(SHALL).
초기 지원 대상은 CN7N 2025 한국어 매뉴얼이며 원본 PDF는 수정하거나 배포해서는 안 된다(MUST NOT).

#### Scenario: Register the supported manual
- **WHEN** CN7N 2025 PDF의 크기와 해시가 지정한 manifest 항목과 일치한다
- **THEN** 시스템은 등록된 메타데이터와 문서 식별자를 반환하고 원본 바이트를 보존한다

#### Scenario: Reject mismatched input
- **WHEN** 파일이 없거나 해시·크기·문서 적용 범위가 입력 메타데이터와 일치하지 않는다
- **THEN** 등록을 실패로 표시하고 기존 정상 등록 결과를 변경하지 않는다

#### Scenario: Preserve uncertain provenance
- **WHEN** 기록된 출처 URL을 검증하지 못했거나 주소 형식이 의심스럽다
- **THEN** 원래 기록과 미검증 상태를 보존하며 추측한 URL을 생성하거나 검증된 링크로 표시하지 않는다

### Requirement: Traceable page and content extraction

시스템은 추출 결과를 문서, 1부터 시작하는 PDF 페이지 번호, 확인된 인쇄 페이지 번호,
절 경로 및 원본 내 위치와 연결해야 한다(SHALL). 알 수 없는 인쇄 페이지와 절은 미확인으로
남겨야 하며 문서 전체에 일정한 페이지 오프셋이 있다고 가정해서는 안 된다(MUST NOT).

#### Scenario: Distinguish page numbering systems
- **WHEN** 대표 매뉴얼의 PDF 13페이지와 16페이지를 처리한다
- **THEN** 인쇄 번호 `1-7`과 `1-10`을 각각 별도로 기록하여 해당 원본 페이지로 돌아갈 수 있다

#### Scenario: Preserve reading order
- **WHEN** 제목과 두 단의 본문이 있는 평가 페이지를 처리한다
- **THEN** 추출 결과의 제목·문단 순서가 원문에서 확인한 읽기 순서와 일치한다

### Requirement: Preserve table meaning and applicability

시스템은 표의 행·열 제목, 값, 단위, 각주, 경고 및 적용 조건의 연결을 보존해야 한다(SHALL).
관계를 확인할 수 없는 구간은 검토 필요로 표시하고 답변용 근거로 승인해서는 안 된다(MUST NOT).

#### Scenario: Preserve tire table conditions
- **WHEN** PDF 13페이지의 타이어 표를 추출한다
- **THEN** 주행 조건과 앞뒤 위치에 맞는 값·단위를 구분하고 관련 각주를 함께 추적한다

#### Scenario: Distinguish transmission rows
- **WHEN** PDF 16페이지의 오일 표에서 수동변속기 행과 DCT 행을 추출한다
- **THEN** 각 행의 변속기 적용 범위를 보존하고 DCT의 기어오일과 제어오일 항목도 구분한다

### Requirement: Explicit coverage and extraction failures

시스템은 모든 PDF 페이지에 처리 상태를 남기고 성공, 검토 필요, OCR 필요, 확인된 빈 페이지,
실패를 구분해야 한다(SHALL). 텍스트가 있다는 이유로 그림 속 정보까지 처리됐다고 판단하거나
빈 추출 결과를 자동으로 성공으로 분류해서는 안 된다(MUST NOT).

#### Scenario: Empty or image-dependent content
- **WHEN** 텍스트가 추출되지 않거나 답에 필요한 정보가 그림에만 있다
- **THEN** 검토 또는 OCR·그림 처리 필요 상태를 기록하고 해당 구간을 검증된 근거에서 제외한다

#### Scenario: Partial document processing
- **WHEN** 일부 페이지가 실패하고 나머지 페이지가 추출됐다
- **THEN** 페이지별 오류와 전체 누락 현황을 보고하며 부분 처리 결과를 전체 성공으로 표시하지 않는다

### Requirement: Reproducible and non-destructive processing

시스템은 원본 해시와 파서·설정 버전으로 처리 결과를 구분하고 같은 입력의 재실행이
중복 등록을 만들지 않게 해야 한다(SHALL). 저장 중 실패하면 이전 정상 결과를 유지하고,
설정 변경 시 다시 생성할 데이터 범위를 표시해야 한다(SHALL).

#### Scenario: Repeat or change parsing configuration
- **WHEN** 같은 원본과 설정으로 재실행하거나 파서 설정만 바꿔 실행한다
- **THEN** 전자는 같은 결과 식별자로 중복을 방지하고 후자는 새 파싱 결과와 하위 색인 재생성 필요를 표시한다

#### Scenario: Interrupted save
- **WHEN** 새 파싱 결과 저장 도중 오류가 발생한다
- **THEN** 이전 정상 결과를 계속 읽을 수 있고 불완전한 결과는 활성 결과로 노출되지 않는다

### Requirement: Contained data writes

시스템은 외부 입력인 파일명·경로·메타데이터를 검증하고 생성물을 설정한 데이터 디렉터리
안에만 기록해야 한다(SHALL). 원본 위치에는 생성물을 쓰지 않아야 한다(SHALL).

#### Scenario: Path escapes the output root
- **WHEN** 파일명이나 출력 경로가 상위 디렉터리 이동 또는 링크 해석으로 허용된 출력 루트 밖을 가리킨다
- **THEN** 작업을 거부하고 루트 밖 파일과 원본을 변경하지 않는다
