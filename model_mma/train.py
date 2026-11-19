"""격투기 모델 학습과 성능 시험.

모델 두 개를 만듭니다.
    승자 모델   A가 이길 확률
    방식 모델   이긴 선수가 어떤 방식(KO/TKO, 서브미션, 판정)으로 이길지
두 확률을 곱해 6가지 조합(선수 2명 x 방식 3가지) 중 가장 확률이 높은 조합을 AI의 답으로 고릅니다.
Man vs AI 격투기 회차는 승자와 방식을 모두 맞혀야 1점이라, 이렇게 고르는 것이 점수 기대값이 가장 높습니다.

레드/블루 코너 정보는 쓰지 않습니다. 승자 모델은 각 경기를 A와 B 순서를 바꿔 두 번 학습하고,
예측할 때도 두 순서의 평균을 내서 선수 순서가 결과에 영향을 주지 않게 합니다.

기간 나누기 (시간 순서를 지킵니다):
    학습   2005 ~ 2022       (그 이전 경기는 선수 기록을 쌓는 데만 씀)
    검증   2023 ~ 2024       모델 고르기
    시험   2025 ~ 지금       마지막에 한 번만 채점 (여기 점수가 '진짜 실력')
그 뒤 고른 설정 그대로, 2005년부터의 모든 경기로 다시 학습해 models/model.pkl 로 저장합니다.

사용법:
    python model_mma/train.py
"""
import json
import pathlib
import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from features import METHODS, WIN_FEATURES, build, method_matrix, win_matrix

ROOT = pathlib.Path(__file__).parent
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"

START = "2005-01-01"
VALID_START = "2023-01-01"
TEST_START = "2025-01-01"
SEED = 7

FEATURE_KO = {
    "elo": "엘로 레이팅", "age": "나이", "height": "키", "reach": "리치", "southpaw": "사우스포",
    "log_fights": "UFC 경기 수", "layoff": "공백 기간", "debut": "UFC 데뷔전",
    "slpm": "분당 유효타", "sapm": "분당 피격", "str_acc": "유효타 적중률", "str_def": "타격 방어율",
    "td15": "테이크다운", "td_acc": "테이크다운 성공률", "td_def": "테이크다운 방어율", "sub15": "서브미션 시도",
    "kd15": "다운 뺏기", "kd_abs15": "다운 당하기",
    "win_ko": "KO승 비율", "win_sub": "서브미션승 비율", "win_dec": "판정승 비율",
    "loss_ko": "KO패 비율", "loss_sub": "서브미션패 비율", "loss_dec": "판정패 비율",
    "recent": "최근 3경기", "streak": "연승·연패",
}


# ---------- 모델 ----------
def win_candidates():
    return {
        # 절편 없이: 두 선수 입력값이 같으면 정확히 50%
        "로지스틱 회귀": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, fit_intercept=False, max_iter=3000)),
        "그래디언트 부스팅": HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=60,
            l2_regularization=1.0, random_state=SEED),
    }


def method_candidates():
    return {
        "로지스틱 회귀": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=3000)),
        "그래디언트 부스팅": HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=60,
            l2_regularization=1.0, random_state=SEED),
    }


def fit_win(model, df):
    """A-B, B-A 두 순서로 학습."""
    X = pd.concat([win_matrix(df), win_matrix(df, swap=True)], ignore_index=True)
    y = np.concatenate([(df.winner == "A").astype(int), (df.winner == "B").astype(int)])
    model.fit(X, y)
    return model


def p_a_wins(model, df):
    """A가 이길 확률. 두 순서의 평균이라 선수 순서와 상관없습니다."""
    p1 = model.predict_proba(win_matrix(df))[:, 1]
    p2 = model.predict_proba(win_matrix(df, swap=True))[:, 1]
    return (p1 + (1 - p2)) / 2


def fit_method(model, df):
    model.fit(method_matrix(df, (df.winner == "A").to_numpy()), df.method)
    return model


def p_method(model, df, winner_is_a):
    """[KO/TKO, 서브미션, 판정] 순서의 확률"""
    proba = model.predict_proba(method_matrix(df, winner_is_a))
    order = [list(model.classes_).index(m) for m in METHODS]
    return proba[:, order]


def combo_proba(win_model, method_model, df):
    """6가지 조합 확률: [A KO, A 서브, A 판정, B KO, B 서브, B 판정]"""
    pa = p_a_wins(win_model, df)
    ma = p_method(method_model, df, True)
    mb = p_method(method_model, df, False)
    return np.hstack([pa[:, None] * ma, (1 - pa)[:, None] * mb])


def combo_label(df):
    """실제 결과 -> 0~5"""
    return (np.where(df.winner == "A", 0, 3) + df.method.map({m: i for i, m in enumerate(METHODS)})).to_numpy()


# ---------- 기준선 ----------
def baseline_combo(df, rule):
    """비교용 단순 규칙. 승자는 엘로가 높은 선수(같으면 경기 수 많은 선수)."""
    a_pick = (df.A_elo > df.B_elo) | ((df.A_elo == df.B_elo) & (df.A_log_fights >= df.B_log_fights))
    if rule == "판정":
        m = np.full(len(df), 2)
    else:  # 그 선수가 가장 많이 이긴 방식
        cols = ["win_ko", "win_sub", "win_dec"]
        a_m = df[[f"A_{c}" for c in cols]].to_numpy().argmax(1)
        b_m = df[[f"B_{c}" for c in cols]].to_numpy().argmax(1)
        m = np.where(a_pick, a_m, b_m)
    return np.where(a_pick, 0, 3) + m


# ---------- 그림 ----------
def korean_font():
    for name in ("Noto Sans CJK KR", "NanumGothic", "AppleGothic", "Malgun Gothic"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def importance_chart(model, df, path):
    """승자 모델에서 입력값별 중요도 (섞었을 때 예측이 얼마나 나빠지는지)"""
    X = pd.concat([win_matrix(df), win_matrix(df, swap=True)], ignore_index=True)
    y = np.concatenate([(df.winner == "A").astype(int), (df.winner == "B").astype(int)])
    r = permutation_importance(model, X, y, scoring="neg_log_loss", n_repeats=10, random_state=SEED)
    imp = np.clip(r.importances_mean, 0, None)
    share = imp / imp.sum() * 100 if imp.sum() > 0 else imp
    names = [FEATURE_KO[f[2:]] for f in WIN_FEATURES]
    top = np.argsort(share)[-12:]
    korean_font()
    fig, ax = plt.subplots(figsize=(7, 5.5))
    ax.barh([names[i] for i in top], share[top], color="#D97757")
    for i, v in enumerate(share[top]):
        ax.text(v + 0.5, i, f"{v:.0f}%", va="center", fontsize=10)
    ax.set_xlabel("승자 예측에 미친 영향 (%)")
    ax.set_title("AI가 중요하게 본 것 (격투기, 상위 12개)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return {WIN_FEATURES[i][2:]: round(float(share[i]), 1) for i in np.argsort(-share)}


# ---------- 실행 ----------
def main():
    MODEL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    table, _, _ = build()
    table = table[table.Date >= START]
    decided = table[table.winner.notna()]                    # 승자가 있는 경기 (승자 모델)
    full = decided[decided.method.notna()]                   # 승자와 방식이 다 있는 경기 (방식 모델, 채점)

    split = lambda d: (d[d.Date < VALID_START], d[(d.Date >= VALID_START) & (d.Date < TEST_START)], d[d.Date >= TEST_START])
    w_tr, w_va, w_te = split(decided)
    m_tr, m_va, m_te = split(full)

    # 1) 검증 기간으로 모델 고르기 (log loss가 낮을수록 확률이 정확함)
    print("== 검증 기간 (2023~2024) ==")
    win_scores = {}
    for name, m in win_candidates().items():
        fit_win(m, w_tr)
        p = p_a_wins(m, w_va)
        y = (w_va.winner == "A").astype(int)
        win_scores[name] = log_loss(y, p, labels=[0, 1])
        print(f"승자 {name:10s} log loss {win_scores[name]:.4f}  적중률 {accuracy_score(y, p >= 0.5):.1%}")
    method_scores = {}
    for name, m in method_candidates().items():
        fit_method(m, m_tr)
        p = p_method(m, m_va, (m_va.winner == "A").to_numpy())
        method_scores[name] = log_loss(m_va.method, p, labels=METHODS)
        print(f"방식 {name:10s} log loss {method_scores[name]:.4f}  적중률 {accuracy_score(m_va.method, np.array(METHODS)[p.argmax(1)]):.1%}")
    win_name = min(win_scores, key=win_scores.get)
    method_name = min(method_scores, key=method_scores.get)
    print(f"선택: 승자 {win_name}, 방식 {method_name}")

    # 2) 학습+검증으로 다시 학습한 뒤 시험 기간을 한 번만 채점
    win_model = fit_win(win_candidates()[win_name], pd.concat([w_tr, w_va]))
    method_model = fit_method(method_candidates()[method_name], pd.concat([m_tr, m_va]))

    pa = p_a_wins(win_model, w_te)
    y_w = (w_te.winner == "A").to_numpy()
    combo = combo_proba(win_model, method_model, m_te)
    pick = combo.argmax(1)
    truth = combo_label(m_te)
    pick_winner_a = pick < 3
    winner_right = pick_winner_a == (m_te.winner == "A").to_numpy()
    fav_a = combo[:, :3].sum(1) >= 0.5

    test = {
        "경기 수 (승패 결정)": int(len(w_te)),
        "경기 수 (채점 가능)": int(len(m_te)),
        "승자 적중률": round(float(((pa >= 0.5) == y_w).mean()) * 100, 1),
        "승자 log loss": round(float(log_loss(y_w.astype(int), pa, labels=[0, 1])), 4),
        "AI 점수 (승자+방식 모두 적중)": round(float((pick == truth).mean()) * 100, 1),
        "AI 답의 승자가 맞은 비율": round(float(winner_right.mean()) * 100, 1),
        "승자가 맞았을 때 방식 적중률": round(float((pick == truth)[winner_right].mean()) * 100, 1),
        "AI가 유력하지 않은 선수를 고른 비율": round(float((pick_winner_a != fav_a).mean()) * 100, 1),
        "AI가 고른 방식 분포": {METHODS[i]: int(((pick % 3) == i).sum()) for i in range(3)},
        "실제 방식 분포": {m: int((m_te.method == m).sum()) for m in METHODS},
        "기준선: 엘로 높은 선수 승자 적중률": round(float(((w_te.A_elo > w_te.B_elo) == y_w).mean()) * 100, 1),
        "기준선: 엘로 높은 선수 + 판정": round(float((baseline_combo(m_te, "판정") == truth).mean()) * 100, 1),
        "기준선: 엘로 높은 선수 + 그 선수가 가장 많이 이긴 방식": round(float((baseline_combo(m_te, "주특기") == truth).mean()) * 100, 1),
    }
    print("\n== 시험 기간 (2025~) ==")
    for k, v in test.items():
        print(f"{k}: {v}")

    results = {"승자 모델": win_name, "방식 모델": method_name,
               "기간": {"학습": f"{START[:4]}~2022", "검증": "2023~2024", "시험": f"2025~{str(table.Date.max().date())}"},
               "시험 기간": test}
    results["승자 모델 중요도(%)"] = importance_chart(win_model, w_te, REPORT_DIR / "feature_importance.png")

    # 3) 2005년부터의 모든 경기로 최종 학습 후 저장
    final_win = fit_win(win_candidates()[win_name], decided)
    final_method = fit_method(method_candidates()[method_name], full)
    with open(MODEL_DIR / "model.pkl", "wb") as f:
        pickle.dump({"win": final_win, "method": final_method, "win_name": win_name, "method_name": method_name,
                     "trained_through": str(table.Date.max().date())}, f)
    (REPORT_DIR / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n저장: models/model.pkl (마지막 학습 경기 {table.Date.max().date()})")


if __name__ == "__main__":
    main()
