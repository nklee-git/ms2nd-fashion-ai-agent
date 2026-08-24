# Fashion AI Agent Appservice (가칭)
> MS 데이터스쿨 5기 · 2차 프로젝트

패션 특화 AI 기반 통합 앱서비스를 만드는 프로젝트입니다. 패션 버티컬 서비스이지만 마케팅·SCM·재무관리 등 다양한 테마를 함께 구체화하며, **Dynamics 365/Dataverse 위에 얹는 패션 버티컬 AI SCM 애드온**(B2B 버티컬 SaaS)을 지향합니다.

## 프로젝트 준비 완료
- 가상데이터 설계문서 35개 → **108만 건의 가상 브랜드 데이터** 생성 완료. 팀원은 데이터를 어떻게 가져올지 고민할 필요 없이, 처음부터 자기 파트의 기술 구현에 집중할 수 있습니다.
- 핵심 데모: 품절위험 SKU를 ML이 예측 → Dataverse에 발주추천 생성 → Teams Adaptive Card 승인 → 원클릭 발주 확정. 발표도 이 흐름이 실제로 동작하는 라이브 데모로 진행합니다.
- ML, RAG, 백엔드(Azure), 프론트엔드 등 롤별로 나눠 협업하는 구조입니다.

## 어디서부터 볼지
1. [00.README.md](00.README.md) — 폴더 구성 3줄 요약
2. [01.PLANNING/11.KickOFF.md](<01.PLANNING/11.KickOFF.md>) — 프로젝트 방향성 전체 (여기부터 읽기 추천)
3. [00.WBS/01. PM TODO board.md](<00.WBS/01. PM TODO board.md>) — 지금 뭘 하고 있는지
4. [20.ARCHITECTURE/24. 기능명세서 v1.md](<20.ARCHITECTURE/24. 기능명세서 v1.md>) — 크로스커팅 계약 + 롤별 TBD
5. [01.PLANNING/13. 팀 온보딩 체크리스트.md](<13. 팀 온보딩 체크리스트.md>) — 합류 직후 준비사항

## 참고
- `30.DATA/32. nqnq_data/*.db`(약 500MB, 생성된 가상 DB)는 GitHub 용량 제한으로 저장소에서 제외되어 있습니다. 필요하면 같은 폴더의 `generate_v4.py`를 로컬에서 실행해 재생성하세요.

관심 있으신 분은 댓글/DM 주세요 🙌
