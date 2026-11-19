"""격투기 한 경기 예측.

사용법:
    python model_mma/predict.py 페레이라 안칼라예프 --date 2026-12-07 --weight 라이트헤비급 --rounds 5
    python model_mma/predict.py "Alex Pereira" "Magomed Ankalaev" --date 2026-12-07 --weight 93

선수 순서는 결과에 영향을 주지 않습니다 (두 순서의 평균을 냅니다).
UFC 경기 기록만 쓰므로, 다른 단체에서 뛴 기록은 반영되지 않습니다.

예측 전에 최신 결과를 반영하려면:
    python model_mma/fetch_data.py
"""
import argparse
import datetime as dt
import difflib
import pathlib
import pickle

import pandas as pd

from features import METHODS, WEIGHT_KG, build
from train import combo_proba

ROOT = pathlib.Path(__file__).parent

ALIASES = {
    "추성훈": "Yoshihiro Akiyama", "아키야마": "Yoshihiro Akiyama",
    "리벤": "Chris Leben", "크리스리벤": "Chris Leben",
    "정찬성": "Chan Sung Jung", "김동현": "Dong Hyun Kim",
    "페레이라": "Alex Pereira", "안칼라예프": "Magomed Ankalaev",
    "존존스": "Jon Jones", "마카체프": "Islam Makhachev", "토푸리아": "Ilia Topuria",
}
WEIGHT_KO = {
    "스트로급": "Strawweight", "플라이급": "Flyweight", "밴텀급": "Bantamweight", "페더급": "Featherweight",
    "라이트급": "Lightweight", "웰터급": "Welterweight", "미들급": "Middleweight",
    "라이트헤비급": "Light Heavyweight", "헤비급": "Heavyweight",
}


def resolve(name, fighters):
    key = name.replace(" ", "")
    full = ALIASES.get(key, name)
    if full in fighters:
        return full
    close = difflib.get_close_matches(full, list(fighters), n=5, cutoff=0.6)
    raise SystemExit(f"'{name}' 을(를) UFC 기록에서 찾지 못했습니다." + (f" 비슷한 이름: {', '.join(close)}" if close else ""))


def parse_weight(w):
    if w is None:
        return None
    w = w.replace(" ", "")
    if w in WEIGHT_KO:
        return WEIGHT_KG[WEIGHT_KO[w]]
    try:
        return float(w)
    except ValueError:
        raise SystemExit(f"체급은 {', '.join(WEIGHT_KO)} 또는 kg 숫자로 입력하세요.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--date", help="경기 날짜, 예: 2026-12-07 (빼면 오늘)")
    ap.add_argument("--weight", help="체급 (예: 미들급) 또는 kg")
    ap.add_argument("--rounds", type=int, choices=[3, 5], default=3)
    ap.add_argument("--women", action="store_true")
    args = ap.parse_args()

    with open(ROOT / "models" / "model.pkl", "rb") as f:
        saved = pickle.load(f)
    _, fighters, bio = build()
    a, b = resolve(args.a, fighters), resolve(args.b, fighters)
    date = pd.Timestamp(args.date or dt.date.today().isoformat())

    fa, fb = fighters[a], fighters[b]
    row = {"five_rounds": int(args.rounds == 5), "women": int(args.women)}
    weight = parse_weight(args.weight)
    row["weight_kg"] = weight if weight is not None else 75
    row.update({f"A_{k}": v for k, v in fa.features(date, bio.get(a)).items()})
    row.update({f"B_{k}": v for k, v in fb.features(date, bio.get(b)).items()})
    df = pd.DataFrame([row])

    p = combo_proba(saved["win"], saved["method"], df)[0]
    pa = p[:3].sum()
    labels = [(a, m) for m in METHODS] + [(b, m) for m in METHODS]
    best = int(p.argmax())

    print(f"{a} vs {b} · {date.date()} · {args.rounds}라운드")
    for name, f in ((a, fa), (b, fb)):
        last = f.last.date() if f.last is not None else "없음"
        print(f"  {name}: UFC {f.n}경기, 엘로 {f.elo:.0f}, 마지막 UFC 경기 {last}")
    print()
    print(f"승리 확률  {a} {pa:.1%} · {b} {1 - pa:.1%}")
    for (name, m), q in sorted(zip(labels, p), key=lambda x: -x[1]):
        print(f"  {name:22s} {m:6s} {q:6.1%}")
    print(f"AI의 답: {labels[best][0]} {labels[best][1]}")
    warn = [n for n, f in ((a, fa), (b, fb)) if f.last is not None and (date - f.last).days > 3 * 365]
    if warn:
        print(f"주의: {', '.join(warn)} 은(는) 마지막 UFC 경기가 3년 넘게 지나 예측 신뢰도가 낮습니다.")
    print(f"(모델 학습: {saved['trained_through']}까지의 UFC 경기)")


if __name__ == "__main__":
    main()
