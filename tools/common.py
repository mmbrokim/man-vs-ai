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

ANSWERS = ["홈승", "무", "원정승"]
# 동률일 때 우선순위: 실제로 더 자주 일어나는 결과 순서 (프리미어리그 10시즌 기준 홈승 45%, 원정승 32%, 무 23%)
TIE_ORDER = ["홈승", "원정승", "무"]
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


def majority(votes):
    """{'홈승': n, '무': n, '원정승': n} -> 가장 많은 답. 동률이면 TIE_ORDER 순서."""
    best = max(votes.values())
    for answer in TIE_ORDER:
        if votes.get(answer, 0) == best:
            return answer


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
