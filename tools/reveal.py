"""결과 편: AI 원문 공개와 경기 결과 기록.

사용법:
    축구 (스코어는 홈-원정):
    python tools/reveal.py 1 --score 2-1

    격투기 (winner: 1 레드 코너 / 2 블루 코너 / 3 무승부 / 4 무효, method: 1 KO/TKO / 2 서브미션 / 3 판정)
    승자와 승리 방식을 모두 맞혀야 맞힌 것입니다. 무승부와 무효 경기는 채점하지 않습니다.
    python tools/reveal.py 2 --winner 1 --method 1 --round 2

    private 파일을 잃어버렸을 때:
    python tools/reveal.py 1 --score 2-1 --text "EP1|홈승|..."

하는 일:
    1) private/originals.json 의 원문을 다시 해시해서 seals.json 의 봉인값과 같은지 확인합니다.
    2) 같을 때만 revealed_text 에 원문을 기록합니다.
    3) 경기 결과를 기록합니다.
"""
import argparse

from common import (FOOTBALL, MMA_DRAW, MMA_METHODS, MMA_NO_CONTEST, MMA_UNSCORED, ORIGINALS, SEALS, find, load_json,
                    normalize, outcome_from_score, parse_text, save_json, sha256, sport_of)


def pick(raw, options, what):
    raw = normalize(str(raw))
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    if raw in options:
        return raw
    menu = ", ".join(f"{i} {o}" for i, o in enumerate(options, 1))
    raise SystemExit(f"{what}은(는) 다음 중 하나여야 합니다: {menu}")


def ox(answer, method, result):
    """answer/method: 예측, result: seals.json 의 result"""
    if not answer:
        return "집계 없음"
    shown = f"{answer} {method}" if method else answer
    if result["outcome"] in MMA_UNSCORED:
        return f"{shown} (채점 안 함: {result['outcome']})"
    hit = answer == result["outcome"] and (method is None or method == result.get("method"))
    return f"{shown} {'O' if hit else 'X'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", type=int)
    ap.add_argument("--score", help="축구: 경기 스코어 (홈-원정), 예: 2-1")
    ap.add_argument("--winner", help="격투기: 1 레드 / 2 블루 / 3 무승부 / 4 무효")
    ap.add_argument("--method", help="격투기: 1 KO/TKO / 2 서브미션 / 3 판정")
    ap.add_argument("--round", type=int, help="격투기: 끝난 라운드 (선택)")
    ap.add_argument("--text")
    args = ap.parse_args()

    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 EP{args.ep} 이 없습니다.")
    if seal.get("revealed_text"):
        raise SystemExit(f"EP{args.ep} 은 이미 공개되어 있습니다: {seal['revealed_text']}")

    if sport_of(seal) == FOOTBALL:
        if not args.score:
            raise SystemExit("축구 회차는 --score 2-1 (홈-원정) 이 필요합니다.")
        outcome = outcome_from_score(args.score)
        result = {"score": args.score.replace(" ", ""), "outcome": outcome}
        summary = f"{args.score} → {outcome}"
    else:
        if not args.winner:
            raise SystemExit("격투기 회차는 --winner 가 필요합니다 (1 레드 / 2 블루 / 3 무승부 / 4 무효).")
        outcome = pick(args.winner, [seal["fighter_a"], seal["fighter_b"], MMA_DRAW, MMA_NO_CONTEST], "승자")
        if outcome in MMA_UNSCORED:
            method = None
        else:
            if not args.method:
                raise SystemExit("--method 가 필요합니다 (1 KO/TKO / 2 서브미션 / 3 판정).")
            method = pick(args.method, MMA_METHODS, "승리 방식")
        result = {"outcome": outcome, "method": method, "round": args.round}
        summary = " · ".join(str(x) for x in [outcome, method, f"{args.round}R" if args.round else None] if x)

    if args.text:
        text = normalize(args.text)
    else:
        originals = load_json(ORIGINALS, {})
        if str(args.ep) not in originals:
            raise SystemExit(f"private/originals.json 에 EP{args.ep} 원문이 없습니다. --text 로 직접 입력하세요.")
        text = originals[str(args.ep)]["text"]

    if sha256(text) != seal["hash"]:
        raise SystemExit("중단: 원문의 해시가 봉인값과 다릅니다. 원문을 확인하세요.")

    seal["revealed_text"] = text
    seal["result"] = result
    save_json(SEALS, seals)

    ai = parse_text(text)
    human = seal.get("human") or {}
    print(f"EP{args.ep} 공개 완료: {text} (해시 일치 확인)")
    print(f"경기 결과: {summary}")
    print(f"AI: {ox(ai['pick'], ai['method'], result)}")
    print(f"사람: {ox(human.get('pick'), human.get('method'), result)}")
    print(f"다음 순서: git add public && git commit -m \"EP{args.ep} 공개\" && git push")


if __name__ == "__main__":
    main()
