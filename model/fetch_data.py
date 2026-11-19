"""경기 데이터 내려받기.

football-data.co.uk 에서 프리미어리그(E0)와 챔피언십(E1) CSV를 받아 data/ 에 저장합니다.
챔피언십은 승격팀의 엘로 레이팅을 계산하기 위해 함께 받습니다.

사용법:
    python model/fetch_data.py            # 전체 시즌 (이미 받은 지난 시즌은 건너뜀)
    python model/fetch_data.py --refresh  # 지난 시즌도 다시 받기
"""
import argparse
import datetime as dt
import pathlib
import urllib.request

DATA_DIR = pathlib.Path(__file__).parent / "data"
BASE = "https://www.football-data.co.uk/mmz4281/{code}/{div}.csv"
DIVISIONS = ["E0", "E1"]
FIRST_SEASON = 2016  # 2016-17 시즌부터


def season_codes(today=None):
    """'1617', '1718', ... 현재 시즌까지의 코드 목록."""
    today = today or dt.date.today()
    current_start = today.year if today.month >= 7 else today.year - 1
    return [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(FIRST_SEASON, current_start + 1)]


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "man-vs-ai-model"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        path.write_bytes(resp.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="지난 시즌 파일도 다시 받기")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    codes = season_codes()
    current = codes[-1]
    for code in codes:
        for div in DIVISIONS:
            path = DATA_DIR / f"{div}_{code}.csv"
            # 진행 중인 시즌은 매번 새로 받고, 끝난 시즌은 이미 있으면 건너뜀
            if path.exists() and code != current and not args.refresh:
                continue
            download(BASE.format(code=code, div=div), path)
            print(f"받음: {path.name}")
    print("완료")


if __name__ == "__main__":
    main()
