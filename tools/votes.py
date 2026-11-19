"""사람들의 선택을 직접 입력하기 (API를 쓸 수 없을 때 대비용).

사용법:
    python tools/votes.py 1 --home 120 --draw 30 --away 50
"""
import argparse
import datetime as dt

from common import SEALS, find, load_json, majority, save_json

KST = dt.timezone(dt.timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", type=int)
    ap.add_argument("--home", type=int, required=True, help="홈승 표 수")
    ap.add_argument("--draw", type=int, required=True, help="무 표 수")
    ap.add_argument("--away", type=int, required=True, help="원정승 표 수")
    args = ap.parse_args()

    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 EP{args.ep} 이 없습니다.")
    votes = {"홈승": args.home, "무": args.draw, "원정승": args.away}
    if min(votes.values()) < 0 or sum(votes.values()) == 0:
        raise SystemExit("표 수를 확인해 주세요.")

    seal["human"] = {
        "votes": votes,
        "total": sum(votes.values()),
        "pick": majority(votes),
        "cutoff": seal["kickoff"],
        "counted_at": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "source": "manual",
        "votes_file": None,
    }
    save_json(SEALS, seals)
    print(f"EP{args.ep} 사람의 답: {seal['human']['pick']} (총 {seal['human']['total']}표)")


if __name__ == "__main__":
    main()
