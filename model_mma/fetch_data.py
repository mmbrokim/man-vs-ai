"""격투기(UFC) 경기 데이터 내려받기.

UFC 공식 기록 사이트(ufcstats.com)를 정리해 깃허브에 올려 둔 공개 데이터를 받아 data/ 에 저장합니다.
https://github.com/Greco1899/scrape_ufc_stats  (매일 갱신)

받는 파일:
    ufc_event_details.csv   대회 이름, 날짜
    ufc_fight_results.csv   경기 결과, 승리 방식, 라운드, 체급
    ufc_fight_stats.csv     라운드별 타격·테이크다운 기록
    ufc_fighter_tott.csv    선수 키, 리치, 스탠스, 생년월일

사용법:
    python model_mma/fetch_data.py
"""
import pathlib
import urllib.request

DATA_DIR = pathlib.Path(__file__).parent / "data"
BASE = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/{name}"
FILES = ["ufc_event_details.csv", "ufc_fight_results.csv", "ufc_fight_stats.csv", "ufc_fighter_tott.csv"]


def main():
    DATA_DIR.mkdir(exist_ok=True)
    for name in FILES:
        req = urllib.request.Request(BASE.format(name=name), headers={"User-Agent": "man-vs-ai-model"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            (DATA_DIR / name).write_bytes(resp.read())
        print(f"받음: {name}")
    print("완료")


if __name__ == "__main__":
    main()
