# 들썩 KAMIS API 연동

한국농수산식품유통공사 일별 도·소매 가격정보 API 연결 테스트입니다.

1. [GitHub Actions Secrets](https://github.com/send-jinu/jinu/settings/secrets/actions)에서 **New repository secret** 클릭
2. **Name**: `KAMIS_API_KEY` / **Secret**: 공공데이터포털에서 발급한 API 인증키
3. [Actions](https://github.com/send-jinu/jinu/actions/workflows/kamis-test.yml)에서 **Run workflow** 실행
4. 실행 성공 시 Artifacts에서 응답 JSON 다운로드

인증키는 소스코드에 저장하지 않습니다. 현재 코드는 쌀(품목코드 111)의 최근 7일 중도매 가격 연결 테스트이며, 인증 및 데이터 수신은 아직 확인되지 않았습니다.

## 프랜차이즈 공시 매출 분석 웹앱

`franchise/`에 공정거래위원회 가맹사업 공시 매출 조회 앱을 추가했습니다. 서버를 `python3 franchise/server.py`로 실행한 뒤 브라우저에서 `http://127.0.0.1:8000`을 열고 **인증키 설정** 탭에서 공공데이터포털 키를 등록하거나, 실행 전에 `FRANCHISE_SERVICE_KEY` 환경변수를 설정하세요. 상세한 API 설정과 계산 기준은 [franchise/README.md](franchise/README.md)를 참고하세요.

공개 배포는 저장소의 `render.yaml` Blueprint를 사용합니다. Render에서 이 저장소를 연결한 뒤 `FRANCHISE_SERVICE_KEY` 환경변수 입력란에 키를 등록하면 됩니다. 키는 GitHub에 올리지 않습니다.
