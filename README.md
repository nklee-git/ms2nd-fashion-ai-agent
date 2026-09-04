# Fashion AI Agent Appservice (가칭)
> MS 데이터스쿨 5기 · 2차 프로젝트

**SAP 등 기존 ERP는 그대로 두고 그 옆에 붙는 AI 재고 리플레니시먼트(수요계획+발주승인) 포인트 솔루션**을 만드는 프로젝트입니다. 기술 핵심은 **Data Factory+Databricks**(공식 커리큘럼 가이드라인 확인, 2026-09-03), 그 결과를 Dataverse(Power Platform) 기반 Teams 승인 액션으로 연결합니다.

> `30.DATA`는 학습·검증에 쓰는 **가상 데이터 생성 소스**일 뿐 프로젝트의 메인이 아닙니다. NQNQ는 "지그재그가 만든 가상 PB 브랜드"라는 시뮬레이션 배경(가상 고객사)일 뿐 우리 제품명이 아닙니다. 최종 앱서비스 브랜드명은 팀원과 협의해 결정 예정.
> 이 저장소(TeamShare)는 팀 실행에 필요한 간결한 문서만 담습니다 — PM의 상세 변경이력·리서치 원자료·미확정 브레인스토밍은 별도 비공개 PM 저장소에 있습니다.

## 프로젝트 준비 완료
- 가상데이터 설계문서 35개 → **108만 건의 가상 브랜드 데이터** 생성 완료. 팀원은 데이터를 어떻게 가져올지 고민할 필요 없이, 처음부터 자기 파트의 기술 구현에 집중할 수 있습니다.
- 핵심 데모: 품절위험 SKU를 Databricks가 예측 → Dataverse에 발주추천 생성 → Teams Adaptive Card 승인 → 원클릭 발주 확정. 발표도 이 흐름이 실제로 동작하는 라이브 데모로 진행합니다.
- 롤별로 나눠 협업하는 구조입니다(아래 폴더 구성 참고).

## 어디서부터 볼지
1. [01.PLANNING/11. KickOFF.md](<01.PLANNING/11. KickOFF.md>) — 프로젝트 방향성 전체 (여기부터 읽기 추천)
2. [00.WBS/01. PM TODO board.md](<00.WBS/01. PM TODO board.md>) — 지금 뭘 하고 있는지
3. [20.ARCHITECTURE/24. 기능명세서 v1.md](<20.ARCHITECTURE/24. 기능명세서 v1.md>) — 크로스커팅 계약 + 롤별 TBD
4. [01.PLANNING/13. 팀 온보딩 체크리스트.md](<01.PLANNING/13. 팀 온보딩 체크리스트.md>) — 합류 직후 준비사항

## 폴더 구성
두 자릿수 인덱스(대분류 자리 + 소분류 자리) 체계. 폴더 안에서도 문서 성격별로 번호 밴드를 나눠 씀 — 새 문서 만들 때 이 밴드부터 확인하고 맞는 자리에 넣을 것 (그냥 다음 번호로 이어붙이지 말기).

- **00.WBS** — 진행 관리 그 자체(일정·TODO)만 다룸. 기획 내용은 여기 안 옴
  - [00. PM TODO board.md](<00.WBS/01. PM TODO board.md>) · [03. WBS 상세.md](<00.WBS/03. WBS 상세 (기술 레이어별 일정표).md>) · [04. Week 0-3 실행 계획.md](<00.WBS/04. Week 0-3 실행 계획 & 동기화 체크포인트.md>)
- **01.PLANNING** — 기획 단계 문서. 안에서도 성격별 밴드로 나뉨:
  - 11-12 방향성·시장: [11. KickOFF.md](<01.PLANNING/11. KickOFF.md>) · [12. Market Research.md](<01.PLANNING/12. Market Research.md>)(요약본)
  - 13 팀 준비: [13. 팀 온보딩 체크리스트.md](<01.PLANNING/13. 팀 온보딩 체크리스트.md>)
  - 16 발표 전략: [16. PPT plan.md](<01.PLANNING/16. PPT plan.md>)
- **20.ARCHITECTURE** — 기술 설계·확정 스펙. [24. 기능명세서 v1.md](<20.ARCHITECTURE/24. 기능명세서 v1.md>)가 유일한 원본(크로스커팅 계약)이고, 21·22번은 겹치는 내용을 24번으로 링크만 겁니다
  - [21. Appservice Core model.md](<20.ARCHITECTURE/21. Appservice Core model.md>) · [22. Cost Plan.md](<20.ARCHITECTURE/22. Cost Plan.md>) · [23. Alert & Trigger Rules.md](<20.ARCHITECTURE/23. Alert & Trigger Rules.md>) · [24. 기능명세서 v1.md](<20.ARCHITECTURE/24. 기능명세서 v1.md>) · [25. AI 책임원칙 체크리스트.md](<20.ARCHITECTURE/25. AI 책임원칙 체크리스트.md>)
- **30.DATA** — 가상 데이터 생성 소스 (브랜드 기획 문서 `31. NQNQ_data Frame`, 생성 스크립트 `32. nqnq_data`, `nqnq.db`, 타임라인 엑셀은 `31. NQNQ_data Frame` 안에 있음)
- **40/50/60 — 롤별 구현 폴더** (각자 핵심 롤 기준). 진행상황은 여기서 관리 안 함 — PM TODO board 하나로만 통합 추적. 안엔 41/42/43(또는 51/52/53, 61/62/63)처럼 밴드 번호를 이어서 하위 넘버링:
  - **40. 데이터·인프라**(Data Factory·Dataverse·Power Automate·Teams) — 41.설계노트 · 42.작업 스냅샷 · 43.캡처
  - **50. ML·Databricks**(기술 핵심) — 51.설계노트 · 52.작업 스냅샷(Databricks Repos로 이 저장소 직접 연결 가능) · 53.캡처
  - **60. 대시보드**(React+Power BI) — 61.설계노트 · 62.저장소 링크(React는 별도 GitHub 저장소 권장) · 63.캡처

> 아직 안 쓰는 대역(70 등)은 실제로 그 성격의 문서가 생기면 그때 추가.

## 데이터는 어디서 오나
[30.DATA](<30.DATA/31. NQNQ_data Frame/00. Home/NQNQ Basic Frame.md>) 폴더의 108만 건 가상 주문 데이터(`32. nqnq_data/nqnq.db`)를 학습·예측 대상으로 사용합니다. 브랜드 기획 디테일(SKU, 재고정책 등)이 궁금하면 그 폴더를 참고하세요 — 이 프로젝트 자체의 기획 문서는 아닙니다.

## 참고
- `30.DATA/32. nqnq_data/*.db`(약 500MB, 생성된 가상 DB)는 GitHub 용량 제한으로 저장소에서 제외되어 있습니다. 필요하면 같은 폴더의 `generate_v4.py`를 로컬에서 실행해 재생성하세요.
