"""유튜브 댓글로 사람들의 선택 집계하기 (킥오프 직후 실행).

사용법:
    python tools/tally.py 1 https://youtube.com/shorts/xxxx
    python tools/tally.py 1 xxxx            (영상 ID만 넣어도 됩니다)

API 키 (무료): 환경변수 YT_API_KEY 또는 private/youtube_api_key.txt 파일 한 줄.

집계 규칙 (페이지에도 같은 내용이 적혀 있습니다):
    1) 영상의 최상위 댓글만 셉니다. 답글과 채널 주인 댓글은 세지 않습니다.
    2) 킥오프 전에 쓴 댓글만 셉니다. 킥오프 뒤에 수정된 댓글도 제외합니다.
    3) 인정하는 답: '홈승', '원정승', '무'(또는 '무승부'), 그리고 두 팀 이름.
       팀 이름을 쓰면 그 팀의 승리로 봅니다. 서로 다른 답이 섞인 댓글은 무효입니다.
    4) 한 계정당 한 표. 여러 번 남겼다면 유효한 답이 있는 마지막 댓글을 셉니다.
    5) 가장 많이 나온 답이 사람의 답입니다. 동률이면 홈승 > 원정승 > 무 순서로 정합니다.

결과:
    public/seals.json 의 human 항목에 표 수와 비율을 기록하고,
    집계에 쓴 댓글 ID와 선택을 public/votes/EP{회차}.csv 로 공개합니다 (닉네임은 넣지 않음).
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request

from common import (ANSWERS, PRIVATE_DIR, ROOT, SEALS, find, load_json, majority, normalize,
                    parse_kickoff_iso, save_json)

API = "https://www.googleapis.com/youtube/v3/commentThreads"
VOTES_DIR = ROOT / "public" / "votes"
KST = dt.timezone(dt.timedelta(hours=9))


# ---------- 입력 ----------
def video_id_from(arg):
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", arg)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", arg):
        return arg
    raise SystemExit("영상 주소나 11자리 영상 ID를 넣어 주세요.")


def api_key():
    key = os.environ.get("YT_API_KEY")
    path = PRIVATE_DIR / "youtube_api_key.txt"
    if not key and path.exists():
        key = path.read_text().strip()
    if not key:
        raise SystemExit("API 키가 없습니다. private/youtube_api_key.txt 에 키를 한 줄로 넣어 주세요.")
    return key


def fetch_comments(video_id, key):
    """영상의 최상위 댓글 전부. 100개씩 여러 번 요청합니다 (요청 1번 = 할당량 1)."""
    items, token = [], None
    while True:
        params = {"part": "snippet", "videoId": video_id, "maxResults": 100,
                  "textFormat": "plainText", "order": "time", "key": key}
        if token:
            params["pageToken"] = token
        try:
            with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(params)}", timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"유튜브 API 오류 {e.code}: {e.read().decode()[:300]}")
        items.extend(data.get("items", []))
        token = data.get("nextPageToken")
        if not token:
            return items


# ---------- 답 읽기 ----------
def answer_patterns(match):
    """'맨시티 vs 풀럼' -> 답별 정규식."""
    parts = re.split(r"\s+vs\.?\s+", match, flags=re.I)
    if len(parts) != 2:
        raise SystemExit(f"경기 이름에서 두 팀을 찾지 못했습니다: '{match}' ('홈 vs 원정' 형식이어야 합니다)")
    home, away = (normalize(p) for p in parts)
    not_hangul = r"(?<![가-힣])", r"(?![가-힣])"
    return {
        "홈승": [re.compile("홈승"), re.compile(re.escape(home))],
        "원정승": [re.compile("원정승"), re.compile(re.escape(away))],
        # '무조건', '무리' 같은 단어 속의 '무'는 세지 않도록 앞뒤가 한글이 아닐 때만 인정
        "무": [re.compile("무승부"), re.compile(not_hangul[0] + "무" + not_hangul[1])],
    }


def read_answer(text, patterns):
    text = normalize(text)
    found = {ans for ans, pats in patterns.items() if any(p.search(text) for p in pats)}
    return found.pop() if len(found) == 1 else None


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- 집계 ----------
def tally(items, match, cutoff):
    patterns = answer_patterns(match)
    stats = {"댓글 수": len(items), "킥오프 후 작성·수정": 0, "답 없음·무효": 0, "중복 계정": 0, "채널 주인": 0}
    latest = {}  # 계정 -> (작성 시각, 댓글 ID, 답)
    for it in items:
        top = it["snippet"]["topLevelComment"]
        sn = top["snippet"]
        author = (sn.get("authorChannelId") or {}).get("value")
        if author and author == it["snippet"].get("channelId"):
            stats["채널 주인"] += 1
            continue
        if ts(sn["publishedAt"]) >= cutoff or ts(sn.get("updatedAt", sn["publishedAt"])) >= cutoff:
            stats["킥오프 후 작성·수정"] += 1
            continue
        ans = read_answer(sn.get("textDisplay", ""), patterns)
        if ans is None:
            stats["답 없음·무효"] += 1
            continue
        key = author or f"comment:{top['id']}"
        if key in latest:
            stats["중복 계정"] += 1
            if ts(sn["publishedAt"]) <= latest[key][0]:
                continue
        latest[key] = (ts(sn["publishedAt"]), top["id"], ans)

    rows = sorted(latest.values())
    votes = {a: 0 for a in ANSWERS}
    for _, _, ans in rows:
        votes[ans] += 1
    return votes, rows, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", type=int)
    ap.add_argument("video")
    args = ap.parse_args()

    seals = load_json(SEALS, [])
    seal = find(seals, args.ep)
    if seal is None:
        raise SystemExit(f"seals.json 에 EP{args.ep} 이 없습니다.")
    cutoff = parse_kickoff_iso(seal["kickoff"])
    now = dt.datetime.now(KST)
    if now < cutoff:
        raise SystemExit(f"아직 킥오프 전입니다 ({cutoff:%m-%d %H:%M}). 집계는 킥오프 뒤에 합니다.")

    vid = video_id_from(args.video)
    items = fetch_comments(vid, api_key())
    votes, rows, stats = tally(items, seal["match"], cutoff)
    total = sum(votes.values())
    if total == 0:
        raise SystemExit("유효한 표가 없습니다. 집계를 기록하지 않았습니다.")

    VOTES_DIR.mkdir(parents=True, exist_ok=True)
    votes_file = VOTES_DIR / f"EP{args.ep}.csv"
    with open(votes_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["comment_id", "published_at", "choice"])
        for t, cid, ans in rows:
            w.writerow([cid, t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), ans])

    seal["human"] = {
        "votes": votes,
        "total": total,
        "pick": majority(votes),
        "cutoff": seal["kickoff"],
        "counted_at": now.isoformat(timespec="seconds"),
        "source": "youtube",
        "video_id": vid,
        "votes_file": f"votes/EP{args.ep}.csv",
        "stats": stats,
    }
    if not seal.get("video"):
        seal["video"] = f"https://youtube.com/shorts/{vid}"
    save_json(SEALS, seals)

    print(f"EP{args.ep} 집계 완료 · 총 {total}표")
    for a in ANSWERS:
        print(f"  {a:4s} {votes[a]:5d}표  {votes[a] / total:6.1%}")
    print(f"사람의 답: {seal['human']['pick']}")
    print("제외:", ", ".join(f"{k} {v}" for k, v in stats.items() if k != "댓글 수"))
    print(f"다음 순서: git add public && git commit -m \"EP{args.ep} 집계\" && git push")


if __name__ == "__main__":
    main()
