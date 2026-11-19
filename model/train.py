"""학습과 성능 시험.

시즌 나누기 (시간 순서를 지킵니다):
    학습     2017-18 ~ 2023-24   (2016-17은 엘로가 자리 잡는 준비 기간이라 제외)
    검증     2024-25             모델 고르기 + 무승부 기준값 정하기
    시험     2025-26             마지막에 한 번만 채점 (여기 점수가 '진짜 실력')
그 뒤 고른 설정 그대로, 지금까지의 모든 경기로 다시 학습해 models/model.pkl 로 저장합니다.

기준선 (배당률은 모델에 넣지 않고, 비교용으로만 씁니다):
    항상 홈승       무조건 홈팀 승리를 고름
    배당률 1순위    시장 배당이 가장 낮은(가장 유력한) 결과를 고름

사용법:
    python model/train.py
"""
import json
import pathlib
import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from features import FEATURES, build

ROOT = pathlib.Path(__file__).parent
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"

TRAIN = ["1718", "1819", "1920", "2021", "2122", "2223", "2324"]
VALID = ["2425"]
TEST = ["2526"]
CLASSES = ["A", "D", "H"]  # sklearn 이 정렬하는 순서
LABEL_KO = {"H": "홈승", "D": "무", "A": "원정승"}
FEATURE_KO = {
    "elo_diff": "엘로 레이팅 차이",
    "ppg_h": "홈팀 최근 5경기 승점",
    "ppg_a": "원정팀 최근 5경기 승점",
    "gd_h": "홈팀 최근 득실차",
    "gd_a": "원정팀 최근 득실차",
    "sot_h": "홈팀 유효슈팅 우위",
    "sot_a": "원정팀 유효슈팅 우위",
    "home_ppg_h": "홈팀 홈경기 성적",
    "away_ppg_a": "원정팀 원정경기 성적",
    "rest_h": "홈팀 휴식일",
    "rest_a": "원정팀 휴식일",
}
SEED = 7


def candidates():
    return {
        "로지스틱 회귀": make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000)),
        "그래디언트 부스팅": HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=40,
            l2_regularization=1.0, random_state=SEED),
    }


def pick(proba, draw_threshold):
    """확률 -> 답. 무 확률이 기준값 이상이면 무, 아니면 홈승/원정승 중 높은 쪽."""
    p_a, p_d, p_h = proba[:, 0], proba[:, 1], proba[:, 2]
    out = np.where(p_h >= p_a, "H", "A")
    if draw_threshold is not None:
        out = np.where(p_d >= draw_threshold, "D", out)
    return out


def odds_pick(df):
    odds = df[["odds_A", "odds_D", "odds_H"]].to_numpy(dtype=float)
    return np.array(CLASSES)[np.nanargmin(odds, axis=1)]


MIN_DRAW_SHARE = 0.05  # 무승부 규칙: 최소한 전체 경기의 5%는 무를 고르도록


def choose_threshold(proba, y):
    """무승부 기준값 고르기.
    무를 한 번도 안 고르는 것이 적중률은 가장 높지만, 콘텐츠를 위해 무승부 규칙을 둡니다.
    검증 시즌에서 '무를 5% 이상 고르는' 기준값 중 적중률이 가장 높은 것을 고릅니다."""
    best_t, best_acc = None, -1.0
    for t in np.arange(0.24, 0.40, 0.01):
        t = round(float(t), 2)
        picks = pick(proba, t)
        if (picks == "D").mean() < MIN_DRAW_SHARE:
            continue
        acc = accuracy_score(y, picks)
        if acc > best_acc + 1e-9:
            best_t, best_acc = t, acc
    return best_t, best_acc


def korean_font():
    for name in ("Noto Sans CJK KR", "NanumGothic", "AppleGothic", "Malgun Gothic"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def importance_chart(model, X, y, path):
    r = permutation_importance(model, X, y, scoring="neg_log_loss", n_repeats=20, random_state=SEED)
    imp = np.clip(r.importances_mean, 0, None)
    share = imp / imp.sum() * 100 if imp.sum() > 0 else imp
    order = np.argsort(share)
    korean_font()
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh([FEATURE_KO[FEATURES[i]] for i in order], share[order], color="#D97757")
    for i, v in enumerate(share[order]):
        ax.text(v + 0.5, i, f"{v:.0f}%", va="center", fontsize=10)
    ax.set_xlabel("예측에 미친 영향 (%)")
    ax.set_title("AI가 중요하게 본 것")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return {FEATURES[i]: round(float(share[i]), 1) for i in range(len(FEATURES))}


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    table, _ = build()

    tr = table[table.Season.isin(TRAIN)]
    va = table[table.Season.isin(VALID)]
    te = table[table.Season.isin(TEST)]
    cur = table[table.Season > TEST[-1]]

    # 1) 검증 시즌으로 모델 고르기 (log loss가 낮을수록 확률이 정확함)
    print("== 검증 시즌 (2024-25) ==")
    scores = {}
    for name, m in candidates().items():
        m.fit(tr[FEATURES], tr.FTR)
        p = m.predict_proba(va[FEATURES])
        scores[name] = (log_loss(va.FTR, p, labels=CLASSES), m, p)
        print(f"{name:10s} log loss {scores[name][0]:.4f}  적중률 {accuracy_score(va.FTR, pick(p, None)):.1%}")
    best_name = min(scores, key=lambda k: scores[k][0])
    _, best_model, p_val = scores[best_name]
    threshold, val_acc = choose_threshold(p_val, va.FTR)
    print(f"선택: {best_name}, 무승부 기준값: {threshold} (검증 적중률 {val_acc:.1%})")

    # 2) 학습+검증으로 다시 학습한 뒤 시험 시즌을 한 번만 채점
    final_name_model = candidates()[best_name]
    trva = table[table.Season.isin(TRAIN + VALID)]
    final_name_model.fit(trva[FEATURES], trva.FTR)
    p_test = final_name_model.predict_proba(te[FEATURES])

    def report(df, proba, label):
        y = df.FTR.to_numpy()
        res = {
            "경기 수": int(len(df)),
            "AI 적중률": round(accuracy_score(y, pick(proba, threshold)) * 100, 1),
            "AI log loss": round(log_loss(y, proba, labels=CLASSES), 4),
            "항상 홈승": round(float((y == "H").mean()) * 100, 1),
            "배당률 1순위": round(accuracy_score(y, odds_pick(df)) * 100, 1),
            "AI가 고른 무승부 수": int((pick(proba, threshold) == "D").sum()),
            "실제 무승부 수": int((y == "D").sum()),
        }
        print(f"\n== {label} ==")
        for k, v in res.items():
            print(f"{k:14s} {v}")
        return res

    results = {"선택 모델": best_name, "무승부 기준값": threshold,
               "시험 시즌 2025-26": report(te, p_test, "시험 시즌 2025-26")}
    if len(cur):
        results["이번 시즌 지금까지"] = report(cur, final_name_model.predict_proba(cur[FEATURES]),
                                       "이번 시즌 지금까지 (참고)")

    results["중요도(%)"] = importance_chart(final_name_model, te[FEATURES], te.FTR,
                                          REPORT_DIR / "feature_importance.png")

    # 3) 지금까지의 모든 경기로 최종 학습 후 저장
    allm = table[table.Season >= TRAIN[0]]
    final = candidates()[best_name]
    final.fit(allm[FEATURES], allm.FTR)
    with open(MODEL_DIR / "model.pkl", "wb") as f:
        pickle.dump({"model": final, "name": best_name, "features": FEATURES,
                     "draw_threshold": threshold, "trained_through": str(allm.Date.max().date())}, f)
    (REPORT_DIR / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n저장: models/model.pkl (마지막 학습 경기 {allm.Date.max().date()})")


if __name__ == "__main__":
    main()
