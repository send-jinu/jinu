# 들썩 KAMIS API 연동

한국농수산식품유통공사 일별 도·소매 가격정보 API 연결 테스트입니다.

1. [GitHub Actions Secrets](https://github.com/send-jinu/jinu/settings/secrets/actions)에서 **New repository secret** 클릭
2. **Name**: `KAMIS_API_KEY` / **Secret**: 공공데이터포털에서 발급한 API 인증키
3. [Actions](https://github.com/send-jinu/jinu/actions/workflows/kamis-test.yml)에서 **Run workflow** 실행
4. 실행 성공 시 Artifacts에서 응답 JSON 다운로드

인증키는 소스코드에 저장하지 않습니다. 현재 코드는 쌀(품목코드 111)의 최근 7일 중도매 가격 연결 테스트이며, 인증 및 데이터 수신은 아직 확인되지 않았습니다.
