# 리뷰 크롤러 베이스 코드

Google Play와 Apple App Store의 공개 리뷰를 JSON Lines 형태로 수집하는 Python 3 스크립트입니다.  
공식 개발자 API 없이 공개 피드/크롤러 라이브러리만 사용합니다.

## 주요 기능
- 공통 데이터 모델(`ReviewRecord`)로 두 스토어 리뷰를 동일 포맷으로 변환 (app_name 포함)
- Google Play: `google-play-scraper` 최신순 리뷰 크롤링
- Apple App Store: iTunes Customer Reviews RSS(JSON) 직접 호출
- JSON Lines 출력(파일 또는 stdout), `--install-missing`로 의존성 자동 설치 지원
- Google Play 언어 설정: 국가코드에 따라 lang을 자동 매핑(KR→ko, US/UK→en 등)
- 앱 이름은 파일명/출력용으로 소문자 ASCII 슬러그로 정규화(e.g., "TikTok - Videos, Shop & LIVE" → "tiktok-videos-shop-live")
- OpenAI 연동을 위한 분석 모듈/엔드포인트 추가(요약 등)

## 설치/준비
로컬에 Python 3.10+ 권장. 필요 시 의존성 자동 설치 옵션 사용:
```bash
python3 fetch_reviews.py --store app-store --app-id 544007664 --install-missing --max-pages 1
```
수동 설치 시:
```bash
python3 -m pip install requests google-play-scraper
```

## 사용법
- ```bash
# Google Play (패키지명으로)
python3 fetch_reviews.py \
  --store google \
  --app-id com.netflix.mediaclient \
  --country kr \
  --max-pages 3 \
  --install-missing

# Apple App Store (앱 ID로)
python3 fetch_reviews.py \
  --store apple \
  --app-id 544007664 \
  --country us \
  --max-pages 5 \
  --install-missing

# Apple App Store (앱 이름으로 검색 → ID/이름 자동 탐색)
python3 fetch_reviews.py \
  --store apple \
  --app-name "TikTok" \
  --country us \
  --max-pages 1 \
  --install-missing

# Google Play (앱 이름으로 검색 → ID/이름 자동 탐색)
python3 fetch_reviews.py \
  --store google \
  --app-name "Netflix" \
  --country us \
  --max-pages 1 \
  --install-missing
```
- 출력 경로는 자동으로 `outputs/{store}_{appId}_{appName}_{country}_{UTCYYYYMMDDHHMM}.jsonl`로 생성됩니다(UTC 기준, 분 단위, app_name이 없으면 app_id를 사용).
- `--max-pages`는 스토어/라이브러리 페이지 개념에 맞춰 반복 호출 횟수로 해석
- API 서버로 사용하려면 FastAPI/uvicorn을 설치 후 실행:
  ```bash
  # 자동 설치 옵션 포함 실행
  python3 run_api.py --install-missing --port 8000
  # 또는 직접 실행
  python3 -m pip install fastapi uvicorn
  python3 -m uvicorn api.main:app --reload --port 8000
  ```
  호출 예시:
  ```bash
  curl -X POST "http://localhost:8000/fetch" \
    -H "Content-Type: application/json" \
    -d '{"store":"apple","app_name":"TikTok","country":"us","max_pages":1,"install_missing":true}'
  ```
  요약/분석 예시(저장된 JSONL 사용, OPENAI_API_KEY 필요):
  ```bash
  curl -X POST "http://localhost:8000/analyze" \
    -H "Content-Type: application/json" \
    -d '{"file_path":"outputs/app-store_1235601864_tiktok_kr_202512050319.jsonl","max_items":30,"install_missing":true}'
  ```

## 모듈 구조
- `reviews_crawler/models.py`: `ReviewRecord` 정의 및 시간/직렬화 헬퍼
- `reviews_crawler/google_play_client.py`: Google Play 리뷰 수집 래퍼
- `reviews_crawler/apple_app_store_client.py`: Apple 리뷰 RSS 수집기
- `reviews_crawler/cli.py`: argparse 기반 CLI, `--install-missing` 지원
- `api/main.py`: FastAPI 기반 로컬 API 서버(POST /fetch, POST /analyze, GET /health)
- `fetch_reviews.py`: 실행 진입점
- `run_api.py`: API 서버 실행 스크립트(부족한 패키지 자동 설치 옵션)
- `reviews_crawler/analysis_service.py`: JSONL 리뷰 파싱 및 OpenAI 요약 호출
- `reviews_crawler/config.py`: OpenAI 키/모델/최대 리뷰 수 설정 로더

## 출력/결과 확인
- 모든 실행 결과는 자동으로 `outputs/` 아래에 저장됩니다.
- 파일명 패턴: `store_appId_appName_country_UTCYYYYMMDDHHMM.jsonl` (예: `app-store_835599320_tiktok_us_202512051055.jsonl`)
- 저장된 JSONL 파일을 분석 모듈에서 바로 읽어 사용할 수 있습니다.

## 추가 옵션/동작
- `--store`: `google` 또는 `apple` 사용 (내부적으로 google-play / app-store로 매핑)
- `--app-name`: 이름으로 검색하여 ID를 찾습니다(스토어별 검색 API 사용). app_id만 있을 경우에는 lookup API로 공식 앱 이름을 채워 출력/파일명에 활용합니다.
- 출력 레코드의 `app_name` 필드는 찾은 이름(또는 전달한 이름)이 들어갑니다.

## 주의사항
- 네트워크 정책/robots를 준수하는 소규모 수집용 PoC 수준입니다.
- 실제 서비스 전 사용 시 대상 스토어 약관을 다시 확인하세요.
