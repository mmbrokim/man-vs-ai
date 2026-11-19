"""AI의 답 봉인하기.

사용법:
    python tools/seal.py
        (종목, 회차, 경기, 시작 시각, 답을 차례로 물어봅니다)

    축구:
    python tools/seal.py --ep 1 --match "맨시티 vs 풀럼" --kickoff "2026-11-21 21:30" --answer 홈승

    격투기 (선수 이름은 번호로 고릅니다: 1 = 레드 코너, 2 = 블루 코너):
    python tools/seal.py --sport mma --ep 2 --event "UFC 323" --fighter-a 페레이라 --fighter-b 안칼라예프 \\
        --kickoff "2026-12-07 12:00" --answer 1 --method 1

회차 번호는 종목과 상관없이 하나로 이어서 셉니다.

하는 일:
    1) 16자 랜덤 문자열을 만들어 원문을 만듭니다.
         축구:   EP{회차}|{홈승|무|원정승}|{랜덤}
         격투기: EP{회차}|{이긴 선수}|{KO/TKO|서브미션|판정}|{랜덤}   (무승부는 선택지에 없음)
    2) 원문은 private/originals.json 에만 저장합니다. (git, Vercel 모두 올라가지 않음)
    3) public/seals.json 에는 해시만 추가합니다.
    4) 영상에 넣을 해시를 출력합니다.
"""
import argparse
import datetime as dt
import secrets
import string

from common import (ANSWERS, FOOTBALL, MMA, MMA_METHODS, ORIGINALS, SEALS, SPORTS,
                    assert_private_is_ignored, check_name, find, load_json, normalize, save_json, sha256)

SALT_LEN = 16
SALT_ALPHABET = string.ascii_letters + string.digits  # '|' 나 공백은 들어가지 않음
KST = dt.timezone(dt.timedelta(hours=9))


def ask(prompt, value):
    return value if value not in (None, "") else input(prompt).strip()


def pick(raw, options, what):
    """번호(1, 2, 3…) 또는 정확한 이름으로 고르기."""
    raw = normalize(str(raw))
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    if raw in options:
        return raw
    menu = ", ".join(f"{i} {o}" for i, o in enumerate(options, 1))
    raise SystemExit(f"{what}은(는) 다음 중 하나여야 합니다: {menu}")


def menu(options):
    return " / ".join(f"{i} {o}" for i, o in enumerate(options, 1))


def parse_kickoff(raw):
    try:
        t = dt.datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        raise SystemExit("시각은 '2026-11-21 21:30' 형식(한국 시간)으로 입력하세요.")
    return t.replace(tzinfo=KST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", help="football 또는 1 (축구) / mma 또는 2 (격투기)")
    ap.add_argument("--ep", type=int)
    ap.add_argument("--kickoff", help="한국 시간, 예: 2026-11-21 21:30")
    ap.add_argument("--answer", help="축구: 홈승/무/원정승 또는 1/2/3 · 격투기: 1 레드 / 2 블루")
    # 축구
    ap.add_argument("--match", help="축구: '홈 vs 원정'")
    # 격투기
    ap.add_argument("--event", help="격투기: 대회 이름, 예: UFC 323")
    ap.add_argument("--fighter-a", help="격투기: 레드 코너 선수")
    ap.add_argument("--fighter-b", help="격투기: 블루 코너 선수")
    ap.add_argument("--method", help="격투기: 1 KO/TKO / 2 서브미션 / 3 판정")
    args = ap.parse_args()

    assert_private_is_ignored()

    sport = pick(ask("종목 (1 축구 / 2 격투기): ", args.sport), [FOOTBALL, MMA], "종목")
    ep = int(ask("회차 (종목과 상관없이 이어지는 번호): ", args.ep))

    seals = load_json(SEALS, [])
    originals = load_json(ORIGINALS, {})
    if find(seals, ep) or str(ep) in originals:
        raise SystemExit(f"EP{ep} 은 이미 봉인되어 있습니다. 봉인은 다시 할 수 없습니다.")
    last = max((s["ep"] for s in seals), default=0)
    if ep != last + 1:
        print(f"주의: 마지막 회차는 EP{last} 입니다. EP{ep} 으로 봉인합니다.")

    salt = "".join(secrets.choice(SALT_ALPHABET) for _ in range(SALT_LEN))
    entry = {"ep": ep, "sport": sport}

    if sport == FOOTBALL:
        match = normalize(ask("경기 (예: 맨시티 vs 풀럼): ", args.match))
        kickoff = parse_kickoff(ask("킥오프 (한국 시간, 예: 2026-11-21 21:30): ", args.kickoff))
        answer = pick(ask(f"답 ({menu(ANSWERS)}): ", args.answer), ANSWERS, "답")
        text = f"EP{ep}|{answer}|{salt}"
        entry.update({"match": match})
    else:
        event = normalize(ask("대회 (예: UFC 323): ", args.event))
        a = check_name(ask("레드 코너 선수: ", args.fighter_a))
        b = check_name(ask("블루 코너 선수: ", args.fighter_b))
        if a == b:
            raise SystemExit("두 선수 이름이 같습니다.")
        kickoff = parse_kickoff(ask("경기 시작 예정 (한국 시간, 메인카드 시작 시각): ", args.kickoff))
        answer = pick(ask(f"이길 선수 ({menu([a, b])}): ", args.answer), [a, b], "이길 선수")
        method = pick(ask(f"승리 방식 ({menu(MMA_METHODS)}): ", args.method), MMA_METHODS, "승리 방식")
        text = f"EP{ep}|{answer}|{method}|{salt}"
        entry.update({"event": event, "fighter_a": a, "fighter_b": b, "match": f"{a} vs {b}"})

    if kickoff <= dt.datetime.now(KST):
        print("주의: 시작 시각이 이미 지났습니다. 봉인은 경기 전에 해야 의미가 있습니다.")

    digest = sha256(text)

    # 원문을 먼저 비공개 파일에 저장하고, 그다음에 해시를 공개 파일에 씁니다.
    originals[str(ep)] = {"text": text, "sealed_at": dt.datetime.now(KST).isoformat(timespec="seconds")}
    save_json(ORIGINALS, originals)

    entry.update({
        "kickoff": kickoff.isoformat(timespec="minutes"),
        "hash": digest,
        "video": None,
        "revealed_text": None,
        "human": None,
        "result": None,
    })
    seals.append(entry)
    seals.sort(key=lambda s: s["ep"])
    save_json(SEALS, seals)

    print()
    print(f"[{SPORTS[sport]}] EP{ep} {entry['match']}")
    print(f"원문 (비공개, 결과 편 전까지 아무에게도 보여 주지 마세요): {text}")
    print("  → private/originals.json 에 저장했습니다.")
    print()
    print("영상에 넣을 봉인값:")
    print(digest)
    print()
    print("다음 순서: git add public/seals.json && git commit -m \"EP%d 봉인\" && git push" % ep)


if __name__ == "__main__":
    main()
