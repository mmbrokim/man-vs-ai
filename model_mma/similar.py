"""스타일이 비슷한 선수 찾기와 스타일 맞대결 기록 (참고용 분석).

두 선수의 UFC 통산 기록으로 '스타일 지문'을 만들고, 비슷한 체급에서 지문이 가장 가까운 선수들을 찾습니다.
그다음 'A와 비슷한 선수'와 'B와 비슷한 선수'가 실제로 맞붙은 경기의 결과와 승리 방식을 모읍니다.

스타일 지문 (선수 통산 기록, 5경기 이상 뛴 선수끼리 표준화):
    분당 유효타·피격, 유효타 적중률·방어율, 테이크다운 시도·성공률·방어율, 서브미션 시도,
    다운 뺏기·당하기, KO승·서브미션승·판정승 비율, KO패·서브미션패 비율

주의: 통산 기록을 쓰는 서술용 분석이라, 모델처럼 미래 정보를 엄격히 막지는 않습니다.
      예측 모델의 입력값으로는 쓰지 않습니다.

사용법:
    python model_mma/similar.py 추성훈 리벤
    python model_mma/similar.py 추성훈 리벤 --top 10 --pool 30
"""
import argparse

import numpy as np
import pandas as pd

from features import build
from predict import resolve

STYLE = ["slpm", "sapm", "str_acc", "str_def", "td15", "td_acc", "td_def", "sub15", "kd15", "kd_abs15",
         "win_ko", "win_sub", "win_dec", "loss_ko", "loss_sub"]
STYLE_KO = {
    "slpm": "분당 유효타", "sapm": "분당 피격", "str_acc": "유효타 적중률", "str_def": "타격 방어율",
    "td15": "테이크다운(15분당)", "td_acc": "테이크다운 성공률", "td_def": "테이크다운 방어율",
    "sub15": "서브미션 시도(15분당)", "kd15": "다운 뺏기(15분당)", "kd_abs15": "다운 당하기(15분당)",
    "win_ko": "KO승 비율", "win_sub": "서브미션승 비율", "win_dec": "판정승 비율",
    "loss_ko": "KO패 비율", "loss_sub": "서브미션패 비율",
}
MIN_FIGHTS = 5


def profiles(table, fighters, bio):
    """선수별 통산 스타일 지문과 주 체급(kg)"""
    rows = {}
    for name, f in fighters.items():
        if f.n < MIN_FIGHTS:
            continue
        feat = f.features(f.last, bio.get(name))
        rows[name] = {k: feat[k] for k in STYLE}
        rows[name]["fights"] = f.n
        rows[name]["last"] = f.last
    prof = pd.DataFrame.from_dict(rows, orient="index")
    w = pd.concat([table[["A", "weight_kg"]].rename(columns={"A": "name"}),
                   table[["B", "weight_kg"]].rename(columns={"B": "name"})]).groupby("name").weight_kg.median()
    prof["weight_kg"] = w.reindex(prof.index)
    return prof


def neighbours(prof, z, name, k, weight_gap=10):
    me = prof.loc[name]
    ok = (prof.weight_kg - me.weight_kg).abs() <= weight_gap
    d = np.sqrt(((z.loc[ok] - z.loc[name]) ** 2).sum(1)).drop(name, errors="ignore")
    return d.sort_values().head(k)


def describe(prof, z, name):
    """평균과 가장 다른 특징 4개"""
    top = z.loc[name].abs().sort_values(ascending=False).head(4).index
    return ", ".join(f"{STYLE_KO[c]} {'높음' if z.loc[name, c] > 0 else '낮음'}" for c in top)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--top", type=int, default=8, help="보여 줄 비슷한 선수 수")
    ap.add_argument("--pool", type=int, default=25, help="맞대결 기록을 모을 비슷한 선수 수")
    args = ap.parse_args()

    table, fighters, bio = build()
    a, b = resolve(args.a, fighters), resolve(args.b, fighters)
    prof = profiles(table, fighters, bio)
    for n in (a, b):
        if n not in prof.index:
            raise SystemExit(f"{n} 은(는) UFC {MIN_FIGHTS}경기 미만이라 스타일 지문을 만들 수 없습니다.")
    z = (prof[STYLE] - prof[STYLE].mean()) / prof[STYLE].std()

    pools = {}
    for n in (a, b):
        near = neighbours(prof, z, n, args.pool)
        pools[n] = set(near.index) | {n}
        print(f"■ {n} (UFC {int(prof.loc[n, 'fights'])}경기) — {describe(prof, z, n)}")
        for other, dist in near.head(args.top).items():
            print(f"   {other:26s} 거리 {dist:4.2f}  UFC {int(prof.loc[other, 'fights'])}경기")
        print()

    # 스타일 맞대결: A쪽 무리 vs B쪽 무리
    pa, pb = pools[a] - pools[b], pools[b] - pools[a]
    m = table[((table.A.isin(pa)) & (table.B.isin(pb))) | ((table.A.isin(pb)) & (table.B.isin(pa)))]
    m = m[m.winner.notna() & ~(m.A.isin([a, b]) & m.B.isin([a, b]))]   # 두 선수의 직접 대결은 빼고 셈
    if m.empty:
        print("두 스타일이 맞붙은 경기가 없습니다.")
        return
    a_side = np.where(m.A.isin(pa), "A", "B")
    a_won = (m.winner.to_numpy() == a_side)
    print(f"■ 스타일 맞대결: '{a}형' vs '{b}형' {len(m)}경기")
    print(f"   {a}형 {a_won.sum()}승 · {b}형 {(~a_won).sum()}승")
    for label, mask in ((f"{a}형 승리", a_won), (f"{b}형 승리", ~a_won)):
        counts = m.method[mask].value_counts()
        print(f"   {label} 방식: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print()
    for _, g in m.sort_values("Date").iterrows():
        w = g.A if g.winner == "A" else g.B
        print(f"   {g.Date.date()}  {g.A} vs {g.B} → {w} ({g.method})")


if __name__ == "__main__":
    main()
