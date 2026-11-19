"""회차에 영상 링크 넣기.

사용법:
    python tools/video.py 1 https://youtube.com/shorts/xxxx
"""
import argparse

from common import SEALS, find, load_json, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", type=int)
    ap.add_argument("url")
    args = ap.parse_args()

    if not args.url.startswith("https://"):
        raise SystemExit("링크는 https:// 로 시작해야 합니다.")
    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 EP{args.ep} 이 없습니다.")
    seal["video"] = args.url
    save_json(SEALS, seals)
    print(f"EP{args.ep} 영상 링크를 넣었습니다: {args.url}")


if __name__ == "__main__":
    main()
