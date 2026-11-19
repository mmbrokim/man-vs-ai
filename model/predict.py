"""한 경기 예측.

사용법:
    python model/predict.py 맨시티 풀럼 --date 2026-11-21
    (첫 번째가 홈팀, 두 번째가 원정팀. 날짜를 빼면 오늘 날짜로 계산)

예측 전에 최신 결과를 반영하려면:
    python model/fetch_data.py
(모델 자체를 다시 학습할 필요는 없습니다. 입력값은 실행할 때마다 최신 데이터로 다시 계산됩니다.)
"""
import argparse
import datetime as dt
import pathlib
import pickle

import pandas as pd

from features import build

ROOT = pathlib.Path(__file__).parent
LABEL_KO = {"H": "홈승", "D": "무", "A": "원정승"}

ALIASES = {
    "아스널": "Arsenal", "애스턴빌라": "Aston Villa", "빌라": "Aston Villa",
    "본머스": "Bournemouth", "브렌트퍼드": "Brentford", "브라이턴": "Brighton",
    "첼시": "Chelsea", "코번트리": "Coventry", "크리스털팰리스": "Crystal Palace", "팰리스": "Crystal Palace",
    "에버턴": "Everton", "풀럼": "Fulham", "헐": "Hull", "헐시티": "Hull", "입스위치": "Ipswich",
    "리즈": "Leeds", "리버풀": "Liverpool", "맨시티": "Man City", "맨체스터시티": "Man City",
    "맨유": "Man United", "맨체스터유나이티드": "Man United", "뉴캐슬": "Newcastle",
    "노팅엄": "Nott'm Forest", "노팅엄포레스트": "Nott'm Forest", "선덜랜드": "Sunderland",
    "토트넘": "Tottenham", "울버햄튼": "Wolves", "울브스": "Wolves", "웨스트햄": "West Ham",
    "레스터": "Leicester", "사우샘프턴": "Southampton", "번리": "Burnley",
}


def resolve(name, state):
    key = name.replace(" ", "")
    team = ALIASES.get(key, name)
    if team not in state.elo:
        known = sorted(t for t, d in state.league.items() if d == "E0")
        raise SystemExit(f"'{name}' 팀을 찾지 못했습니다. 이번 시즌 팀: {', '.join(known)}")
    return team


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--date", help="경기 날짜 YYYY-MM-DD (휴식일 계산용)")
    args = ap.parse_args()

    with open(ROOT / "models" / "model.pkl", "rb") as f:
        bundle = pickle.load(f)
    table, state = build()
    last = table.Date.max()

    home, away = resolve(args.home, state), resolve(args.away, state)
    date = pd.Timestamp(args.date) if args.date else pd.Timestamp(dt.date.today())
    if date <= last:
        raise SystemExit(f"경기 날짜({date.date()})가 데이터의 마지막 경기({last.date()})보다 빠릅니다.")

    feats = state.features(home, away, date)
    X = pd.DataFrame([feats])[bundle["features"]]
    proba = dict(zip(bundle["model"].classes_, bundle["model"].predict_proba(X)[0]))

    t = bundle["draw_threshold"]
    if t is not None and proba["D"] >= t:
        answer = "D"
    else:
        answer = "H" if proba["H"] >= proba["A"] else "A"

    print(f"{home} (홈) vs {away} (원정) · {date.date()}")
    print(f"데이터 기준: {last.date()} 경기까지 반영 · 모델: {bundle['name']}")
    print(f"  홈승   {proba['H']:.1%}")
    print(f"  무     {proba['D']:.1%}")
    print(f"  원정승 {proba['A']:.1%}")
    print(f"AI의 답: {LABEL_KO[answer]}")
    print(f"(엘로 {state.elo[home]:.0f} vs {state.elo[away]:.0f})")


if __name__ == "__main__":
    main()
