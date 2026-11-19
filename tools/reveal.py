"""결과 편: AI 원문 공개와 경기 결과 기록.

사용법:
    python tools/reveal.py 1 --score 2-1
    python tools/reveal.py 1 --score 2-1 --text "EP1|홈승|..."   (private 파일을 잃어버렸을 때)

하는 일:
    1) private/originals.json 의 원문을 다시 해시해서 seals.json 의 봉인값과 같은지 확인합니다.
    2) 같을 때만 revealed_text 에 원문을 기록합니다.
    3) 경기 스코어(홈-원정)와 결과(홈승/무/원정승)를 기록합니다.
"""
import argparse

from common import ORIGINALS, SEALS, find, load_json, normalize, outcome_from_score, save_json, sha256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", type=int)
    ap.add_argument("--score", required=True, help="경기 스코어 (홈-원정), 예: 2-1")
    ap.add_argument("--text")
    args = ap.parse_args()

    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 EP{args.ep} 이 없습니다.")
    if seal.get("revealed_text"):
        raise SystemExit(f"EP{args.ep} 은 이미 공개되어 있습니다: {seal['revealed_text']}")
    outcome = outcome_from_score(args.score)

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
    seal["result"] = {"score": args.score.replace(" ", ""), "outcome": outcome}
    save_json(SEALS, seals)

    ai = text.split("|")[1]
    human = (seal.get("human") or {}).get("pick")
    print(f"EP{args.ep} 공개 완료: {text} (해시 일치 확인)")
    print(f"경기 결과: {args.score} → {outcome}")
    print(f"AI: {ai} {'O' if ai == outcome else 'X'}")
    print(f"사람: {human or '집계 없음'} {'' if not human else ('O' if human == outcome else 'X')}")
    print(f"다음 순서: git add public && git commit -m \"EP{args.ep} 공개\" && git push")


if __name__ == "__main__":
    main()
