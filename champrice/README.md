# 들썩 참가격 GW API — Codex 작업 준비

기존 KAMIS 연동은 유지하고, 참가격 상품·가격 API의 **실제 연결 확인용** 코드를 추가했습니다.

## 1. 인증키 등록
[GitHub Actions Secrets](https://github.com/send-jinu/jinu/settings/secrets/actions) → **New repository secret**

- Name: `CHAMPRICE_SERVICE_KEY`
- Secret: 공공데이터포털 `한국소비자원_생필품 가격 정보_GW`에서 발급받은 인증키

인증키는 채팅·소스코드에 보내지 마세요.

## 2. 실서버 호출
[Champrice GW Live API Check](https://github.com/send-jinu/jinu/actions/workflows/champrice-api-check.yml) → **Run workflow**.

성공하면 Actions 실행 결과에서 상품 수와 가격 레코드 수를 확인하고, `champrice-api-verification` artifact에서 실제 XML 필드명을 확인할 수 있습니다.

## 3. Codex에서 개발 계속하기
[Codex 열기](https://chatgpt.com/codex) → GitHub 저장소 `send-jinu/jinu` 선택.

Codex에 다음 작업을 요청하세요.

> `champrice/AGENTS.md`를 읽고 참가격 GW API 연동을 완성해 주세요. 먼저 Actions의 실제 API 테스트 결과로 상품·가격 XML 구조를 확인하고, 들썩 원가계산기에 상품 검색·가격 조회·원가 환산 기능을 구현하세요. 기존 KAMIS 수집은 유지하고 인증키는 Secret으로만 관리하세요.

**현재 상태:** 실서버 인증키가 설정되기 전이므로 API 연결 성공 여부는 미확인입니다. 기존 원가계산기 HTML은 사용자가 Codex에 제공해야 합니다.
