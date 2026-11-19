"""사람들의 선택을 직접 입력하기 (API를 쓸 수 없을 때 대비용).

사용법:
    축구:   python tools/votes.py 1 --home 120 --draw 30 --away 50
    격투기: python tools/votes.py 2 --red 60 20 40 --blue 30 10 25
            (각 선수의 KO/TKO, 서브미션, 판정 표 수 순서)
"""
import argparse
import datetime as dt

from common import FOOTBALL, MMA_METHODS, SEALS, find, load_json, majority, save_json, sport_of, vote_key

KST = dt.timezone(dt.timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", type=int)
    ap.add_argument("--home", type=int, help="축구: 홈승 표 수")
    ap.add_argument("--away", type=int, help="축구: 원정승 표 수")
    ap.add_argument("--draw", type=int, help="축구: 무 표 수")
    ap.add_argument("--red", type=int, nargs=3, metavar=("KO", "SUB", "DEC"), help="격투기: 레드 코너 KO/TKO 서브미션 판정 표 수")
    ap.add_argument("--blue", type=int, nargs=3, metavar=("KO", "SUB", "DEC"), help="격투기: 블루 코너 KO/TKO 서브미션 판정 표 수")
    args = ap.parse_args()

    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 EP{args.ep} 이 없습니다.")

    if sport_of(seal) == FOOTBALL:
        if None in (args.home, args.draw, args.away):
            raise SystemExit("축구 회차는 --home, --draw, --away 가 필요합니다.")
        votes = {"홈승": args.home, "무": args.draw, "원정승": args.away}
    else:
        if args.red is None or args.blue is None:
            raise SystemExit("격투기 회차는 --red KO SUB DEC --blue KO SUB DEC 가 필요합니다.")
        votes = {}
        for fighter, nums in ((seal["fighter_a"], args.red), (seal["fighter_b"], args.blue)):
            for m, n in zip(MMA_METHODS, nums):
                votes[vote_key(fighter, m)] = n
    if min(votes.values()) < 0 or sum(votes.values()) == 0:
        raise SystemExit("표 수를 확인해 주세요.")

    pick, method = majority(votes, seal)
    seal["human"] = {
        "votes": votes,
        "total": sum(votes.values()),
        "pick": pick,
        "method": method,
        "cutoff": seal["kickoff"],
        "counted_at": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "source": "manual",
        "votes_file": None,
    }
    save_json(SEALS, seals)
    print(f"EP{args.ep} 사람의 답: {pick}{' ' + method if method else ''} (총 {seal['human']['total']}표)")


if __name__ == "__main__":
    main()
