"""입력값(특징) 계산.

핵심 원칙: 어떤 경기의 입력값이든 '그 경기 킥오프 전에 끝난 경기'만 보고 계산합니다.
경기를 날짜순으로 하나씩 지나가면서, 먼저 입력값을 계산하고 그다음에 결과를 반영합니다.
그래서 미래 정보가 섞일 수 없습니다.

입력값 목록 (FEATURES):
    elo_diff      엘로 레이팅 차이 (홈 - 원정)
    ppg_h, ppg_a  최근 5경기 경기당 승점
    gd_h, gd_a    최근 5경기 경기당 득실차
    sot_h, sot_a  최근 5경기 유효슈팅 차이 (내 유효슈팅 - 상대 유효슈팅) 평균
    home_ppg_h    홈팀의 최근 5번 홈경기 경기당 승점
    away_ppg_a    원정팀의 최근 5번 원정경기 경기당 승점
    rest_h, rest_a  직전 경기 후 쉰 날수 (최대 14일)
"""
import math
import pathlib
from collections import defaultdict, deque

import pandas as pd

DATA_DIR = pathlib.Path(__file__).parent / "data"

FEATURES = [
    "elo_diff",
    "ppg_h", "ppg_a",
    "gd_h", "gd_a",
    "sot_h", "sot_a",
    "home_ppg_h", "away_ppg_a",
    "rest_h", "rest_a",
]

# 엘로 설정
K = 20
HOME_ADV = 60          # 엘로 계산 안에서만 쓰는 홈 이점
START_EPL = 1600       # 2016-17 시즌 프리미어리그 팀의 시작 점수
START_CHAMP = 1450     # 같은 시즌 챔피언십 팀의 시작 점수
NEW_TEAM_GAP = 100     # 처음 보는 팀(3부에서 승격): 챔피언십 평균보다 이만큼 낮게 시작
SEASON_REGRESS = 0.2   # 시즌이 바뀔 때 리그 평균 쪽으로 20% 되돌림

WINDOW = 5
MAX_REST = 14


def load_matches():
    """data/ 의 모든 CSV를 읽어 날짜순으로 정렬한 표를 돌려줍니다."""
    frames = []
    for path in sorted(DATA_DIR.glob("E[01]_*.csv")):
        div, code = path.stem.split("_")
        df = pd.read_csv(path, encoding="utf-8-sig", encoding_errors="replace")
        df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR"])
        df = df.copy()
        df["Div"] = div
        df["Season"] = code
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed")
    if "Time" not in df:
        df["Time"] = "15:00"
    df["Time"] = df["Time"].fillna("15:00")
    df = df.sort_values(["Date", "Time", "Div"]).reset_index(drop=True)
    for col in ["FTHG", "FTAG", "HST", "AST"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def goal_mult(gd):
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8


class State:
    """팀별 엘로와 최근 경기 기록을 들고 있는 상태."""

    def __init__(self):
        self.elo = {}
        self.league = {}                       # 팀 -> 'E0' / 'E1'
        self.recent = defaultdict(lambda: deque(maxlen=WINDOW))       # (승점, 득실차, 유효슈팅차)
        self.recent_home = defaultdict(lambda: deque(maxlen=WINDOW))  # 홈경기 승점
        self.recent_away = defaultdict(lambda: deque(maxlen=WINDOW))  # 원정경기 승점
        self.last_date = {}
        self.season = None

    # ---------- 시즌 전환 ----------
    def start_season(self, season, teams_by_div):
        """새 시즌 첫 경기 직전에 호출. 승격·강등팀 처리와 평균 회귀."""
        first = self.season is None
        self.season = season
        if first:
            for t in teams_by_div.get("E0", []):
                self.elo[t] = START_EPL
            for t in teams_by_div.get("E1", []):
                self.elo[t] = START_CHAMP
        else:
            known_champ = [self.elo[t] for t in teams_by_div.get("E1", []) if t in self.elo]
            champ_mean = sum(known_champ) / len(known_champ) if known_champ else START_CHAMP
            for div in ("E0", "E1"):
                for t in teams_by_div.get(div, []):
                    if t not in self.elo:
                        self.elo[t] = champ_mean - NEW_TEAM_GAP
            for div in ("E0", "E1"):
                members = teams_by_div.get(div, [])
                if not members:
                    continue
                mean = sum(self.elo[t] for t in members) / len(members)
                for t in members:
                    self.elo[t] += SEASON_REGRESS * (mean - self.elo[t])
        for div, members in teams_by_div.items():
            for t in members:
                self.league[t] = div

    # ---------- 입력값 ----------
    def features(self, home, away, date):
        def avg(dq, idx=None, default=0.0):
            if not dq:
                return default
            vals = [x if idx is None else x[idx] for x in dq]
            vals = [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
            return sum(vals) / len(vals) if vals else default

        def rest(team):
            if team not in self.last_date:
                return MAX_REST
            return min((date - self.last_date[team]).days, MAX_REST)

        return {
            "elo_diff": self.elo.get(home, START_CHAMP) - self.elo.get(away, START_CHAMP),
            "ppg_h": avg(self.recent[home], 0, 1.3),
            "ppg_a": avg(self.recent[away], 0, 1.3),
            "gd_h": avg(self.recent[home], 1),
            "gd_a": avg(self.recent[away], 1),
            "sot_h": avg(self.recent[home], 2),
            "sot_a": avg(self.recent[away], 2),
            "home_ppg_h": avg(self.recent_home[home], None, 1.5),
            "away_ppg_a": avg(self.recent_away[away], None, 1.1),
            "rest_h": rest(home),
            "rest_a": rest(away),
        }

    # ---------- 결과 반영 ----------
    def update(self, row):
        h, a = row.HomeTeam, row.AwayTeam
        hg, ag = row.FTHG, row.FTAG
        res = row.FTR
        pts_h = {"H": 3, "D": 1, "A": 0}[res]
        pts_a = {"H": 0, "D": 1, "A": 3}[res]

        # 엘로
        eh, ea = self.elo[h], self.elo[a]
        exp_h = 1 / (1 + 10 ** ((ea - (eh + HOME_ADV)) / 400))
        score_h = {"H": 1.0, "D": 0.5, "A": 0.0}[res]
        delta = K * goal_mult(hg - ag) * (score_h - exp_h)
        self.elo[h] = eh + delta
        self.elo[a] = ea - delta

        # 최근 기록
        sot_diff = None
        if not (pd.isna(row.HST) or pd.isna(row.AST)):
            sot_diff = row.HST - row.AST
        self.recent[h].append((pts_h, hg - ag, sot_diff))
        self.recent[a].append((pts_a, ag - hg, None if sot_diff is None else -sot_diff))
        self.recent_home[h].append(pts_h)
        self.recent_away[a].append(pts_a)
        self.last_date[h] = row.Date
        self.last_date[a] = row.Date


def _odds(row):
    """시장 평균 배당률(없으면 Bet365). 기준선 비교 전용."""
    for h, d, a in (("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA"), ("B365H", "B365D", "B365A")):
        vals = [getattr(row, c, None) for c in (h, d, a)]
        if all(v is not None and not pd.isna(v) for v in vals):
            return {"odds_H": float(vals[0]), "odds_D": float(vals[1]), "odds_A": float(vals[2])}
    return {"odds_H": None, "odds_D": None, "odds_A": None}


def build():
    """전체 경기를 훑으며 (프리미어리그 경기의 입력값 표, 마지막 상태)를 돌려줍니다."""
    df = load_matches()
    teams = (
        pd.concat([df[["Season", "Div", "HomeTeam"]].rename(columns={"HomeTeam": "Team"}),
                   df[["Season", "Div", "AwayTeam"]].rename(columns={"AwayTeam": "Team"})])
        .drop_duplicates()
        .groupby(["Season", "Div"])["Team"].apply(list)
    )
    state = State()
    rows = []
    for row in df.itertuples(index=False):
        if row.Season != state.season:
            state.start_season(row.Season, {div: teams.get((row.Season, div), []) for div in ("E0", "E1")})
        if row.Div == "E0":
            feats = state.features(row.HomeTeam, row.AwayTeam, row.Date)
            feats.update(Date=row.Date, Season=row.Season, HomeTeam=row.HomeTeam,
                         AwayTeam=row.AwayTeam, FTR=row.FTR)
            # 배당률은 모델 입력값이 아니라, 성능 비교용 기준선으로만 따로 보관합니다.
            feats.update(_odds(row))
            rows.append(feats)
        state.update(row)
    return pd.DataFrame(rows), state


if __name__ == "__main__":
    table, state = build()
    print(table.tail())
    top = sorted(((v, t) for t, v in state.elo.items() if state.league.get(t) == "E0"), reverse=True)
    print("\n현재 프리미어리그 엘로 순위")
    for v, t in top:
        print(f"{t:16s} {v:7.1f}")
