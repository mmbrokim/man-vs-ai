"""봉인·공개 스크립트가 함께 쓰는 규칙.

정규화 규칙은 public/app.js 의 normalize() 와 반드시 같아야 합니다.
    1) 앞뒤 공백 제거 (아래 TRIM_CHARS 에 있는 문자만)
    2) 유니코드 NFC 정규화 (Mac에서 한글 자모가 분리되는 문제 방지)
    3) UTF-8 바이트로 SHA-256
"""
import hashlib
import json
import pathlib
import subprocess
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEALS = ROOT / "public" / "seals.json"
PRIVATE_DIR = ROOT / "private"
ORIGINALS = PRIVATE_DIR / "originals.json"

# ---------- 종목 ----------
# 회차 번호(EP)는 종목과 상관없이 하나로 이어서 셉니다. 종목은 seals.json 의 sport 칸으로 구분합니다.
# sport 칸이 없는 회차는 축구로 봅니다 (EP1처럼 종목 구분 전에 봉인한 회차).
FOOTBALL = "football"
MMA = "mma"
SPORTS = {FOOTBALL: "축구", MMA: "격투기"}

# 축구 원문: EP{회차}|{홈승|무|원정승}|{랜덤}
ANSWERS = ["홈승", "무", "원정승"]
# 동률일 때 우선순위: 실제로 더 자주 일어나는 결과 순서 (프리미어리그 10시즌 기준 홈승 45%, 원정승 32%, 무 23%)
TIE_ORDER = ["홈승", "원정승", "무"]

# 격투기 원문: EP{회차}|{이긴 선수 이름}|{승리 방식}|{랜덤}
#   예측은 두 선수 중 한 명만 고릅니다 (무승부는 선택지에 없음, 배팅 업체의 2-way 방식).
#   승자와 승리 방식을 모두 맞혀야 1점입니다.
MMA_METHODS = ["KO/TKO", "서브미션", "판정"]
# 승리 방식 동률일 때 우선순위: 실제로 더 자주 일어나는 순서 (UFC 전체 기록 기준 판정 47%, KO/TKO 33%, 서브미션 19%)
MMA_METHOD_TIE_ORDER = ["판정", "KO/TKO", "서브미션"]
# 결과에만 쓰는 값: 무승부와 무효 경기(노 콘테스트)는 채점하지 않습니다 (배팅 업체가 베팅을 무효로 돌려주는 것과 같음).
MMA_DRAW = "무승부"
MMA_NO_CONTEST = "무효"
MMA_UNSCORED = (MMA_DRAW, MMA_NO_CONTEST)
TRIM_CHARS = " \t\n\r\v\f\u00a0\u3000\ufeff"


def normalize(text):
    return unicodedata.normalize("NFC", text.strip(TRIM_CHARS))


def sha256(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sport_of(seal):
    return seal.get("sport") or FOOTBALL


def vote_key(fighter, method):
    return f"{fighter}|{method}"


def choices(seal):
    """회차의 표 항목 (집계 순서 = 화면 순서).
    축구: 홈승, 무, 원정승 / 격투기: '선수|방식' 6가지 (레드 3가지, 블루 3가지)"""
    if sport_of(seal) == MMA:
        return [vote_key(f, m) for f in (seal["fighter_a"], seal["fighter_b"]) for m in MMA_METHODS]
    return list(ANSWERS)


def majority(votes, seal=None):
    """표 -> (사람의 답, 승리 방식 또는 None)

    축구: 가장 많은 답. 동률이면 홈승 > 원정승 > 무.
    격투기: 두 단계로 정합니다.
      1) 승자: 선수별 표를 합쳐 많은 쪽. 동률이면 레드 코너 (레드가 보통 더 유력한 선수이고, UFC 기록상 55~60%를 이김)
      2) 방식: 그 선수에게 간 표 중 가장 많은 방식. 동률이면 판정 > KO/TKO > 서브미션
    """
    if seal is None or sport_of(seal) != MMA:
        best = max(votes.values())
        for answer in TIE_ORDER:
            if votes.get(answer, 0) == best:
                return answer, None
    a, b = seal["fighter_a"], seal["fighter_b"]
    total = {f: sum(votes.get(vote_key(f, m), 0) for m in MMA_METHODS) for f in (a, b)}
    winner = a if total[a] >= total[b] else b
    best = max(votes.get(vote_key(winner, m), 0) for m in MMA_METHODS)
    method = next(m for m in MMA_METHOD_TIE_ORDER if votes.get(vote_key(winner, m), 0) == best)
    return winner, method


def check_name(name):
    """선수 이름 확인. 원문의 칸 구분자 '|' 와 겹치거나 답 이름과 헷갈리면 멈춥니다."""
    name = normalize(name)
    if not name or "|" in name:
        raise SystemExit("선수 이름이 비어 있거나 '|' 가 들어 있습니다.")
    if name in (MMA_DRAW, MMA_NO_CONTEST) or name in MMA_METHODS:
        raise SystemExit(f"'{name}' 은 선수 이름으로 쓸 수 없습니다.")
    return name


def parse_text(text):
    """공개된 원문 -> {'pick': 답, 'method': 승리 방식 또는 None}"""
    parts = normalize(text).split("|")
    if len(parts) == 4:
        return {"pick": parts[1], "method": parts[2]}
    return {"pick": parts[1], "method": None}


def outcome_from_score(score):
    """'2-1' -> '홈승'"""
    try:
        h, a = (int(x) for x in score.replace(" ", "").split("-"))
    except ValueError:
        raise SystemExit("스코어는 '2-1' 형식(홈-원정)으로 입력하세요.")
    return "홈승" if h > a else "원정승" if a > h else "무"


def parse_kickoff_iso(iso):
    import datetime as dt
    return dt.datetime.fromisoformat(iso)


def find(seals, ep):
    for s in seals:
        if s["ep"] == ep:
            return s
    return None


def assert_private_is_ignored():
    """private/ 폴더가 git에 올라가지 않는지 확인합니다. 올라갈 수 있으면 멈춥니다."""
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                                capture_output=True, text=True).returncode == 0
    except FileNotFoundError:
        return  # git이 없으면 확인할 수 없으므로 넘어갑니다
    if not inside:
        return
    probe = "private/originals.json"
    ignored = subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT).returncode == 0
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", probe], cwd=ROOT,
                             capture_output=True).returncode == 0
    if not ignored or tracked:
        raise SystemExit("중단: private/originals.json 이 git에 올라갈 수 있는 상태입니다. "
                         ".gitignore 에 private/ 가 있는지 확인하세요.")
