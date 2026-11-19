"""격투기 입력값(특징) 계산.

핵심 원칙은 축구 모델과 같습니다: 어떤 경기의 입력값이든 '그 날 이전에 끝난 경기'만 보고 계산합니다.
대회 날짜순으로 하루씩 지나가면서, 먼저 그날 모든 경기의 입력값을 계산하고 그다음에 결과를 반영합니다.
(초창기 UFC 토너먼트처럼 한 선수가 하루에 여러 번 싸워도 같은 날 결과가 섞이지 않습니다.)

선수 한 명의 입력값 (FIGHTER_FEATURES):
    elo            엘로 레이팅. KO·서브미션으로 이기면 더 크게 오름
    age            경기 당일 나이
    height, reach  키, 리치 (인치)
    southpaw       사우스포 여부
    log_fights     UFC 경기 수 (log)
    layoff         직전 경기 후 지난 날수 (log)
    debut          UFC 첫 경기 여부
    slpm, sapm     분당 유효타 적중 / 피격
    str_acc        유효타 적중률
    str_def        상대 유효타 방어율
    td15, td_acc   15분당 테이크다운 성공 수, 테이크다운 성공률
    td_def         테이크다운 방어율
    sub15          15분당 서브미션 시도
    kd15, kd_abs15 15분당 다운 뺏은 수 / 당한 수
    win_ko, win_sub, win_dec     경기당 KO/TKO·서브미션·판정 승 비율
    loss_ko, loss_sub, loss_dec  경기당 KO/TKO·서브미션·판정 패 비율
    recent         최근 3경기 승률
    streak         연승(+) 또는 연패(-)

경력이 짧은 선수는 몇 경기 기록만으로 비율이 극단적으로 나오지 않도록, UFC 평균값을 조금 섞어 계산합니다.

데이터에는 UFC 경기만 있습니다. 다른 단체 경기는 들어 있지 않습니다.
"""
import math
import pathlib
from collections import defaultdict, deque

import numpy as np
import pandas as pd

DATA_DIR = pathlib.Path(__file__).parent / "data"

FIGHTER_FEATURES = [
    "elo", "age", "height", "reach", "southpaw", "log_fights", "layoff", "debut",
    "slpm", "sapm", "str_acc", "str_def", "td15", "td_acc", "td_def", "sub15", "kd15", "kd_abs15",
    "win_ko", "win_sub", "win_dec", "loss_ko", "loss_sub", "loss_dec", "recent", "streak",
]

# 승자 모델: 두 선수 입력값의 차이 (A - B). 순서를 바꾸면 부호만 바뀝니다.
WIN_FEATURES = [f"d_{f}" for f in FIGHTER_FEATURES]

# 방식 모델: 이긴 선수(W)와 진 선수(L)의 입력값 + 경기 조건
METHOD_FEATURES = [
    "w_win_ko", "w_win_sub", "w_win_dec", "l_loss_ko", "l_loss_sub", "l_loss_dec",
    "w_slpm", "l_sapm", "w_kd15", "l_kd_abs15", "w_sub15", "w_td15", "l_td_def", "l_str_def",
    "w_age", "l_age", "elo_gap", "five_rounds", "weight_kg", "women",
]

METHODS = ["KO/TKO", "서브미션", "판정"]
METHOD_MAP = {
    "KO/TKO": "KO/TKO", "TKO - Doctor's Stoppage": "KO/TKO",
    "Submission": "서브미션",
    "Decision - Unanimous": "판정", "Decision - Split": "판정", "Decision - Majority": "판정",
}

# 엘로 설정
START_ELO = 1500
K = 32
FINISH_BONUS = 1.25   # KO·서브미션 승부는 판정보다 크게 반영

# UFC 평균값 (경력이 짧은 선수에게 섞는 값)
PRIOR_MIN = 15.0      # 15분어치 평균 기록을 섞음
PRIOR_FIGHTS = 4.0    # 4경기어치 평균 비율을 섞음
AVG = {
    "slpm": 3.6, "str_acc": 0.45, "td15": 1.3, "td_acc": 0.36, "sub15": 0.5, "kd15": 0.25,
    "win_ko": 0.165, "win_sub": 0.10, "win_dec": 0.22,
}

WEIGHT_KG = {
    "Strawweight": 52, "Flyweight": 57, "Bantamweight": 61, "Featherweight": 66, "Lightweight": 70,
    "Welterweight": 77, "Middleweight": 84, "Light Heavyweight": 93, "Heavyweight": 120,
}


# ---------- 읽기 ----------
def _of(series):
    """'41 of 65' -> (41, 65)"""
    parts = series.fillna("0 of 0").astype(str).str.extract(r"(\d+)\s+of\s+(\d+)").fillna(0).astype(int)
    return parts[0], parts[1]


def _mmss(series):
    parts = series.fillna("0:00").astype(str).str.extract(r"(\d+):(\d+)").fillna(0).astype(int)
    return parts[0] * 60 + parts[1]


def weight_class(text):
    """'UFC Women's Bantamweight Title Bout' -> (61, True)"""
    women = "Women" in text
    for name in sorted(WEIGHT_KG, key=len, reverse=True):  # 'Light Heavyweight' 를 'Heavyweight' 보다 먼저
        if name in text:
            return WEIGHT_KG[name], women
    return np.nan, women


def load():
    ev = pd.read_csv(DATA_DIR / "ufc_event_details.csv")
    ev["EVENT"] = ev.EVENT.str.strip()
    ev["Date"] = pd.to_datetime(ev.DATE.str.strip(), format="%B %d, %Y")

    r = pd.read_csv(DATA_DIR / "ufc_fight_results.csv")
    for c in ["EVENT", "BOUT", "OUTCOME", "WEIGHTCLASS", "METHOD", "TIME FORMAT"]:
        r[c] = r[c].astype(str).str.strip()
    r = r.merge(ev[["EVENT", "Date"]], on="EVENT", how="left").dropna(subset=["Date"])
    names = r.BOUT.str.split(r"\s+vs\.\s+", n=1, expand=True)
    r["A"], r["B"] = names[0].str.strip(), names[1].str.strip()
    r = r.dropna(subset=["A", "B"])
    r["winner"] = r.OUTCOME.map({"W/L": "A", "L/W": "B"})          # 무승부·무효는 비어 있음
    r["method"] = r.METHOD.map(METHOD_MAP)                          # 실격·판정 번복 등은 비어 있음
    r["seconds"] = (r.ROUND.astype(int) - 1) * 300 + _mmss(r.TIME)
    rounds = r["TIME FORMAT"].str.extract(r"^(\d+) Rnd")[0].astype(float)
    r["five_rounds"] = ((rounds == 5) | r.WEIGHTCLASS.str.contains("Title")).astype(int)
    wc = r.WEIGHTCLASS.map(weight_class)
    r["weight_kg"] = [w for w, _ in wc]
    r["women"] = [int(f) for _, f in wc]

    s = pd.read_csv(DATA_DIR / "ufc_fight_stats.csv")
    for c in ["EVENT", "BOUT", "FIGHTER"]:
        s[c] = s[c].astype(str).str.strip()
    s["sig_l"], s["sig_a"] = _of(s["SIG.STR."])
    s["td_l"], s["td_a"] = _of(s["TD"])
    s["kd"] = pd.to_numeric(s.KD, errors="coerce").fillna(0)
    s["sub"] = pd.to_numeric(s["SUB.ATT"], errors="coerce").fillna(0)
    stats = s.groupby(["EVENT", "BOUT", "FIGHTER"])[["sig_l", "sig_a", "td_l", "td_a", "kd", "sub"]].sum()

    t = pd.read_csv(DATA_DIR / "ufc_fighter_tott.csv")
    t["FIGHTER"] = t.FIGHTER.astype(str).str.strip()
    t = t[~t.FIGHTER.duplicated(keep=False)]   # 이름이 같은 선수는 신체 정보를 쓰지 않음
    t["height"] = t.HEIGHT.astype(str).str.extract(r"(\d+)' (\d+)").astype(float).pipe(lambda x: x[0] * 12 + x[1])
    t["reach"] = pd.to_numeric(t.REACH.astype(str).str.replace('"', ""), errors="coerce")
    t["dob"] = pd.to_datetime(t.DOB, format="%b %d, %Y", errors="coerce")
    t["southpaw"] = (t.STANCE.astype(str).str.strip() == "Southpaw").astype(int)
    bio = t.set_index("FIGHTER")[["height", "reach", "dob", "southpaw"]].to_dict("index")

    return r.sort_values("Date").reset_index(drop=True), stats, bio


# ---------- 선수 상태 ----------
class Fighter:
    def __init__(self):
        self.elo = START_ELO
        self.n = 0
        self.last = None
        self.results = deque(maxlen=3)
        self.streak = 0
        self.minutes = 0.0
        self.c = defaultdict(float)   # 누적 기록

    def features(self, date, bio):
        c, m = self.c, self.minutes
        rate = lambda x, avg15: (c[x] + avg15 * PRIOR_MIN / 15) / (m + PRIOR_MIN) * 15   # 15분당 (avg15: 15분당 평균)
        frac = lambda num, den, avg, w=10: (c[num] + avg * w) / (c[den] + w)        # 비율
        per_fight = lambda x, avg: (c[x] + avg * PRIOR_FIGHTS) / (self.n + PRIOR_FIGHTS)
        b = bio or {}
        dob = b.get("dob")
        age = (date - dob).days / 365.25 if dob is not None and not pd.isna(dob) else np.nan
        height = b.get("height", np.nan)
        reach = b.get("reach", np.nan)
        if pd.isna(reach):
            reach = height
        layoff = (date - self.last).days if self.last is not None else np.nan
        recent = (sum(self.results) + 0.5 * (3 - len(self.results))) / 3
        return {
            "elo": self.elo,
            "age": age,
            "height": height,
            "reach": reach,
            "southpaw": b.get("southpaw", 0),
            "log_fights": math.log1p(self.n),
            "layoff": math.log1p(min(layoff, 3000)) if not pd.isna(layoff) else math.log1p(365),
            "debut": int(self.n == 0),
            "slpm": rate("sig_l", AVG["slpm"] * 15) / 15,
            "sapm": rate("sig_abs", AVG["slpm"] * 15) / 15,
            "str_acc": frac("sig_l", "sig_a", AVG["str_acc"], 30),
            "str_def": 1 - frac("sig_abs", "sig_opp_a", AVG["str_acc"], 30),
            "td15": rate("td_l", AVG["td15"]),
            "td_acc": frac("td_l", "td_a", AVG["td_acc"], 5),
            "td_def": 1 - frac("td_opp_l", "td_opp_a", AVG["td_acc"], 5),
            "sub15": rate("sub", AVG["sub15"]),
            "kd15": rate("kd", AVG["kd15"]),
            "kd_abs15": rate("kd_abs", AVG["kd15"]),
            "win_ko": per_fight("win_KO/TKO", AVG["win_ko"]),
            "win_sub": per_fight("win_서브미션", AVG["win_sub"]),
            "win_dec": per_fight("win_판정", AVG["win_dec"]),
            "loss_ko": per_fight("loss_KO/TKO", AVG["win_ko"]),
            "loss_sub": per_fight("loss_서브미션", AVG["win_sub"]),
            "loss_dec": per_fight("loss_판정", AVG["win_dec"]),
            "recent": recent,
            "streak": self.streak,
        }


def _expected(a, b):
    return 1 / (1 + 10 ** ((b - a) / 400))


def _record(f, date, minutes, mine, opp, result, method):
    """경기 하나를 선수 기록에 반영. result: 1 승 / 0 패 / 0.5 무 / None 무효"""
    f.n += 1
    f.last = date
    f.minutes += minutes
    if mine is not None:
        f.c["sig_l"] += mine["sig_l"]; f.c["sig_a"] += mine["sig_a"]
        f.c["td_l"] += mine["td_l"]; f.c["td_a"] += mine["td_a"]
        f.c["sub"] += mine["sub"]; f.c["kd"] += mine["kd"]
    if opp is not None:
        f.c["sig_abs"] += opp["sig_l"]; f.c["sig_opp_a"] += opp["sig_a"]
        f.c["td_opp_l"] += opp["td_l"]; f.c["td_opp_a"] += opp["td_a"]
        f.c["kd_abs"] += opp["kd"]
    if result is None:
        return
    f.results.append(result)
    if result == 1:
        f.streak = f.streak + 1 if f.streak > 0 else 1
        if method:
            f.c[f"win_{method}"] += 1
    elif result == 0:
        f.streak = f.streak - 1 if f.streak < 0 else -1
        if method:
            f.c[f"loss_{method}"] += 1
    else:
        f.streak = 0


# ---------- 표 만들기 ----------
def build(until=None):
    """모든 경기를 날짜순으로 지나가며 입력값 표를 만듭니다.

    until: 이 날짜 '전까지'의 경기만 사용 (미래 정보 차단 확인용)
    돌려주는 값: (경기별 입력값 표, 마지막 선수 상태, 선수 신체 정보)
    """
    r, stats, bio = load()
    if until is not None:
        r = r[r.Date < pd.Timestamp(until)]
    fighters = defaultdict(Fighter)
    rows = []

    for date, day in r.groupby("Date", sort=True):
        # 1) 그날 경기들의 입력값을 먼저 모두 계산
        for _, g in day.iterrows():
            fa = fighters[g.A].features(date, bio.get(g.A))
            fb = fighters[g.B].features(date, bio.get(g.B))
            row = {"Date": date, "EVENT": g.EVENT, "A": g.A, "B": g.B,
                   "winner": g.winner, "method": g.method,
                   "five_rounds": g.five_rounds, "weight_kg": g.weight_kg, "women": g.women}
            row.update({f"A_{k}": v for k, v in fa.items()})
            row.update({f"B_{k}": v for k, v in fb.items()})
            rows.append(row)
        # 2) 그다음 결과 반영
        for _, g in day.iterrows():
            a, b = fighters[g.A], fighters[g.B]
            sa = stats.loc[(g.EVENT, g.BOUT, g.A)].to_dict() if (g.EVENT, g.BOUT, g.A) in stats.index else None
            sb = stats.loc[(g.EVENT, g.BOUT, g.B)].to_dict() if (g.EVENT, g.BOUT, g.B) in stats.index else None
            minutes = g.seconds / 60
            method = g.method if isinstance(g.method, str) else None
            if g.winner == "A":
                ra, rb = 1, 0
            elif g.winner == "B":
                ra, rb = 0, 1
            elif g.OUTCOME == "D/D":
                ra, rb = 0.5, 0.5
            else:
                ra = rb = None
            if ra is not None:
                k = K * (FINISH_BONUS if method in ("KO/TKO", "서브미션") else 1)
                ea = _expected(a.elo, b.elo)
                a.elo, b.elo = a.elo + k * (ra - ea), b.elo - k * (ra - ea)
            _record(a, date, minutes, sa, sb, ra, method)
            _record(b, date, minutes, sb, sa, rb, method)

    table = pd.DataFrame(rows)
    return table, fighters, bio


# ---------- 모델 입력 ----------
def fill_bio(df, prefix):
    """신체 정보가 없는 선수는 UFC 평균값으로 채웁니다."""
    df[f"{prefix}age"] = df[f"{prefix}age"].fillna(30.0)
    df[f"{prefix}height"] = df[f"{prefix}height"].fillna(70.5)
    df[f"{prefix}reach"] = df[f"{prefix}reach"].fillna(df[f"{prefix}height"])
    return df


def win_matrix(df, swap=False):
    """승자 모델 입력: A - B 차이. swap=True 면 B - A."""
    df = fill_bio(fill_bio(df.copy(), "A_"), "B_")
    first, second = ("B_", "A_") if swap else ("A_", "B_")
    return pd.DataFrame({f"d_{f}": df[first + f] - df[second + f] for f in FIGHTER_FEATURES})


def method_matrix(df, winner_is_a):
    """방식 모델 입력. winner_is_a: 각 행에서 A가 이긴 선수인지 (True/False 배열 또는 하나의 값)"""
    df = fill_bio(fill_bio(df.copy(), "A_"), "B_")
    wa = pd.Series(winner_is_a, index=df.index) if not np.isscalar(winner_is_a) else pd.Series(winner_is_a, index=df.index)
    w = lambda f: np.where(wa, df[f"A_{f}"], df[f"B_{f}"])
    l = lambda f: np.where(wa, df[f"B_{f}"], df[f"A_{f}"])
    out = pd.DataFrame({
        "w_win_ko": w("win_ko"), "w_win_sub": w("win_sub"), "w_win_dec": w("win_dec"),
        "l_loss_ko": l("loss_ko"), "l_loss_sub": l("loss_sub"), "l_loss_dec": l("loss_dec"),
        "w_slpm": w("slpm"), "l_sapm": l("sapm"), "w_kd15": w("kd15"), "l_kd_abs15": l("kd_abs15"),
        "w_sub15": w("sub15"), "w_td15": w("td15"), "l_td_def": l("td_def"), "l_str_def": l("str_def"),
        "w_age": w("age"), "l_age": l("age"), "elo_gap": w("elo") - l("elo"),
        "five_rounds": df.five_rounds.to_numpy(), "weight_kg": df.weight_kg.fillna(75).to_numpy(),
        "women": df.women.to_numpy(),
    }, index=df.index)
    return out[METHOD_FEATURES]
