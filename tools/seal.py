"""AI의 답 봉인하기.

사용법:
    python tools/seal.py
        (회차, 경기, 킥오프, 답을 차례로 물어봅니다)
    python tools/seal.py --ep 1 --match "맨시티 vs 풀럼" --kickoff "2026-11-21 21:30" --answer 홈승

하는 일:
    1) 16자 랜덤 문자열을 만들어 원문 'EP{회차}|{답}|{랜덤}' 을 만듭니다.
    2) 원문은 private/originals.json 에만 저장합니다. (git, Vercel 모두 올라가지 않음)
    3) public/seals.json 에는 해시만 추가합니다.
    4) 영상에 넣을 해시를 출력합니다.
"""
import argparse
import datetime as dt
import secrets
import string

from common import (ANSWERS, ORIGINALS, SEALS, assert_private_is_ignored, find, load_json,
                    normalize, save_json, sha256)

SALT_LEN = 16
SALT_ALPHABET = string.ascii_letters + string.digits  # '|' 나 공백은 들어가지 않음
KST = dt.timezone(dt.timedelta(hours=9))


def ask(prompt, value):
    return value if value not in (None, "") else input(prompt).strip()


def parse_answer(raw):
    raw = normalize(raw)
    shortcuts = {"1": "홈승", "2": "무", "3": "원정승"}
    raw = shortcuts.get(raw, raw)
    if raw not in ANSWERS:
        raise SystemExit(f"답은 {', '.join(ANSWERS)} 중 하나여야 합니다 (또는 1/2/3).")
    return raw


def parse_kickoff(raw):
    try:
        t = dt.datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        raise SystemExit("킥오프는 '2026-11-21 21:30' 형식(한국 시간)으로 입력하세요.")
    return t.replace(tzinfo=KST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", type=int)
    ap.add_argument("--match")
    ap.add_argument("--kickoff", help="한국 시간, 예: 2026-11-21 21:30")
    ap.add_argument("--answer", help="홈승 / 무 / 원정승 (또는 1 / 2 / 3)")
    args = ap.parse_args()

    assert_private_is_ignored()

    ep = int(ask("회차: ", args.ep))
    match = normalize(ask("경기 (예: 맨시티 vs 풀럼): ", args.match))
    kickoff = parse_kickoff(ask("킥오프 (한국 시간, 예: 2026-11-21 21:30): ", args.kickoff))
    answer = parse_answer(ask("답 (1 홈승 / 2 무 / 3 원정승): ", args.answer))

    seals = load_json(SEALS, [])
    originals = load_json(ORIGINALS, {})
    if find(seals, ep) or str(ep) in originals:
        raise SystemExit(f"EP{ep} 은 이미 봉인되어 있습니다. 봉인은 다시 할 수 없습니다.")
    if kickoff <= dt.datetime.now(KST):
        print("주의: 킥오프 시각이 이미 지났습니다. 봉인은 킥오프 전에 해야 의미가 있습니다.")

    salt = "".join(secrets.choice(SALT_ALPHABET) for _ in range(SALT_LEN))
    text = f"EP{ep}|{answer}|{salt}"
    digest = sha256(text)

    # 원문을 먼저 비공개 파일에 저장하고, 그다음에 해시를 공개 파일에 씁니다.
    originals[str(ep)] = {"text": text, "sealed_at": dt.datetime.now(KST).isoformat(timespec="seconds")}
    save_json(ORIGINALS, originals)

    seals.append({
        "ep": ep,
        "match": match,
        "kickoff": kickoff.isoformat(timespec="minutes"),
        "hash": digest,
        "video": None,
        "revealed_text": None,
        "human": None,
        "result": None,
    })
    seals.sort(key=lambda s: s["ep"])
    save_json(SEALS, seals)

    print()
    print(f"원문 (비공개, 결과 편 전까지 아무에게도 보여 주지 마세요): {text}")
    print(f"  → private/originals.json 에 저장했습니다.")
    print()
    print("영상에 넣을 봉인값:")
    print(digest)
    print()
    print("다음 순서: git add public/seals.json && git commit -m \"EP%d 봉인\" && git push" % ep)


if __name__ == "__main__":
    main()
