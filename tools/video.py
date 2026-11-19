"""회차에 영상 링크 넣기.

사용법:
    python tools/video.py 1 https://youtube.com/shorts/xxxx
"""
import argparse

from common import SEALS, code_of, find, load_json, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", help="회차: 1, EP1, SP1(특별 경기)")
    ap.add_argument("url")
    args = ap.parse_args()

    if not args.url.startswith("https://"):
        raise SystemExit("링크는 https:// 로 시작해야 합니다.")
    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 {args.ep} 이 없습니다.")
    seal["video"] = args.url
    save_json(SEALS, seals)
    print(f"{code_of(seal)} 영상 링크를 넣었습니다: {args.url}")


if __name__ == "__main__":
    main()
