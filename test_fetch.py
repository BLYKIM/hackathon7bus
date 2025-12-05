"""
간단한 통합 테스트 스크립트.
python3 test_fetch.py 를 실행하면
 - App Store(유튜브) 1페이지
 - Google Play(넷플릭스, KR) 1페이지
를 순서대로 수집하여 outputs/ 아래에 JSONL을 생성합니다.
"""

from reviews_crawler.cli import main as cli_main


def run_app_store():
    cli_main(
        [
            "--store",
            "apple",
            "--app-id",
            "544007664",  # YouTube
            "--country",
            "us",
            "--max-pages",
            "1",
            "--install-missing",
        ]
    )


def run_google_play():
    cli_main(
        [
            "--store",
            "google",
            "--app-id",
            "com.netflix.mediaclient",
            "--country",
            "kr",
            "--max-pages",
            "1",
            "--install-missing",
        ]
    )


if __name__ == "__main__":
    run_app_store()
    run_google_play()
