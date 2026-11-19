# Man vs AI

유튜브 쇼츠 시리즈 **Man vs AI**(사람 vs AI 축구 승부 예측 대결)에 쓰는 코드입니다.

- `model/` — AI의 예측을 만드는 머신러닝 모델
- `public/` — 봉인 검증 페이지 (Vercel에 배포되는 유일한 폴더)
- `tools/` — 봉인·집계·공개 스크립트 (내 컴퓨터에서만 실행)
- `private/` — 봉인 원문, API 키 보관 (git, Vercel 모두 올라가지 않음)

## 봉인 검증

AI의 답을 경기 전에 SHA-256 해시로 봉인해 영상에 넣고, 결과 편에서 원문을 공개합니다.
누구나 원문을 해시로 바꿔 영상 속 봉인값과 같은지 확인할 수 있습니다.

- 원문 형식: `EP{회차}|{답}|{랜덤 16자}` 예) `EP1|홈승|aB3dE5fG7hJ9kL2m`
- 답: `홈승`, `무`, `원정승` 중 하나
- 계산 규칙: 앞뒤 공백 제거 → 유니코드 NFC 정규화 → UTF-8 → SHA-256
  (페이지의 `public/app.js`와 `tools/common.py`가 같은 규칙을 씁니다)

### 회차 진행 순서

```bash
# 1. 예측 (경기 전)
python model/fetch_data.py
python model/predict.py 맨시티 풀럼 --date 2026-11-21

# 2. 봉인 (킥오프 전) — 원문은 private/에만, 해시는 public/seals.json에 저장
python tools/seal.py --ep 1 --match "맨시티 vs 풀럼" --kickoff "2026-11-21 21:30" --answer 홈승
git add public/seals.json && git commit -m "EP1 봉인" && git push
#    → 출력된 봉인값을 영상에 넣고 업로드

# 3. 영상 링크 추가 (업로드 후)
python tools/video.py 1 https://youtube.com/shorts/xxxx
git add public/seals.json && git commit -m "EP1 영상 링크" && git push

# 4. 사람들 선택 집계 (킥오프 직후) — 킥오프 전 댓글만 셈
python tools/tally.py 1 https://youtube.com/shorts/xxxx
git add public && git commit -m "EP1 집계" && git push
#    (API를 못 쓸 때: python tools/votes.py 1 --home 120 --draw 30 --away 50)

# 5. 공개 (결과 편) — 원문을 다시 해시해 봉인값과 같을 때만 기록, 스코어는 홈-원정
python tools/reveal.py 1 --score 2-1
git add public && git commit -m "EP1 공개" && git push
```

### 댓글 집계 규칙

1. 최상위 댓글만 셉니다 (답글, 채널 주인 댓글 제외).
2. 킥오프 전에 쓴 댓글만 셉니다. 킥오프 뒤에 수정된 댓글도 제외합니다.
3. `홈승`, `원정승`, `무`(또는 `무승부`), 두 팀 이름을 답으로 인정합니다. 팀 이름은 그 팀의 승리입니다.
   서로 다른 답이 섞인 댓글은 무효입니다. `무조건`처럼 단어 속의 '무'는 세지 않습니다.
4. 한 계정당 한 표. 여러 번 남겼다면 유효한 답이 있는 마지막 댓글을 셉니다.
5. 가장 많이 나온 답이 사람의 답. 동률이면 홈승 > 원정승 > 무 (실제로 더 자주 일어나는 순서, AI 모델과 같은 기준).

집계에 쓴 댓글 ID와 선택은 `public/votes/EP{회차}.csv`로 공개합니다. 닉네임은 넣지 않습니다.

### 유튜브 API 키 (무료, 처음 한 번)

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 만들기
2. API 및 서비스 → 라이브러리 → **YouTube Data API v3** 사용 설정
3. 사용자 인증 정보 → API 키 만들기
4. 키를 `private/youtube_api_key.txt`에 한 줄로 저장 (깃허브에 올라가지 않음)

댓글 100개당 할당량 1을 씁니다. 기본 할당량은 하루 10,000이라 충분합니다.

push하면 Vercel이 자동으로 다시 배포합니다.

**주의**: `private/originals.json`은 어디에도 백업되지 않습니다. 잃어버리면 원문을 공개할 수 없으니,
결과 편 전까지 이 파일을 지우지 마세요. (`seal.py`는 `private/`가 git에서 제외되어 있지 않으면 실행을 멈춥니다.)

### Vercel 연결 (처음 한 번)

1. Vercel → Add New → Project → 이 저장소 선택
2. Framework Preset: **Other**, 나머지 설정은 그대로 (`vercel.json`이 `public/` 폴더만 배포하도록 지정합니다)
3. Deploy

## 예측 모델

프리미어리그 경기 기록만으로 학습한 모델입니다. **배당률은 입력값으로 쓰지 않습니다.**
킥오프 전에 알 수 있는 정보만 보고 홈승 / 무 / 원정승 확률을 계산합니다.

### 입력값

| 입력값 | 설명 |
|---|---|
| 엘로 레이팅 차이 | 경기 결과로 계속 갱신되는 팀 실력 점수의 차이 |
| 최근 5경기 승점 | 홈팀, 원정팀 각각 |
| 최근 5경기 득실차 | 홈팀, 원정팀 각각 |
| 유효슈팅 우위 | 최근 5경기에서 상대보다 유효슈팅을 얼마나 더 했는지 |
| 홈/원정 성적 | 홈팀의 최근 홈경기, 원정팀의 최근 원정경기 승점 |
| 휴식일 | 직전 경기 후 쉰 날수 (최대 14일) |

승격팀의 실력을 제대로 계산하기 위해 2부 리그(챔피언십) 기록도 함께 사용합니다.

### 학습과 시험

| 구분 | 시즌 | 용도 |
|---|---|---|
| 학습 | 2017-18 ~ 2023-24 | 모델 학습 |
| 검증 | 2024-25 | 모델 고르기, 무승부 기준값 정하기 |
| 시험 | 2025-26 | 마지막에 한 번만 채점 |

**2025-26 시즌 시험 결과 (380경기)**

| 방식 | 적중률 |
|---|---|
| AI (이 모델) | 47.9% |
| 항상 홈승 | 42.6% |
| 배당률 1순위 (참고용 기준선) | 49.5% |

자세한 수치는 `model/reports/results.json`, 입력값별 중요도는 `model/reports/feature_importance.png`에 있습니다.

### 무승부 규칙

무승부는 경기마다 확률이 30%를 넘는 일이 드물어서, 가장 높은 확률만 고르면 AI가 무를 거의 고르지 않습니다.
그래서 **무승부 확률이 28% 이상이면 무로 고르는 규칙**을 둡니다.
기준값은 검증 시즌에서 "전체의 5% 이상은 무를 고르는" 조건 아래 적중률이 가장 높은 값으로 정했고, 시리즈 동안 바꾸지 않습니다.

### 사용법

```bash
pip install -r model/requirements.txt

python model/fetch_data.py                               # 최신 경기 결과 받기
python model/train.py                                    # 학습 + 성능 시험 (처음 한 번, 또는 다시 학습할 때)
python model/predict.py 맨시티 풀럼 --date 2026-11-21     # 홈팀 원정팀 순서
```

출력 예시:

```
Man City (홈) vs Fulham (원정) · 2026-11-21
  홈승   67.8%
  무     18.3%
  원정승 13.9%
AI의 답: 홈승
```

### 미래 정보 차단

경기를 날짜순으로 하나씩 지나가면서, 먼저 그 경기의 입력값을 계산하고 그다음에 결과를 반영합니다.
미래 경기를 지우고 다시 계산해도 과거 경기의 입력값이 똑같은지 확인했습니다 (차이 0).

## 데이터 출처

경기 결과 데이터: [football-data.co.uk](https://www.football-data.co.uk/)
데이터 파일은 저장소에 올리지 않습니다. `model/fetch_data.py`로 직접 받습니다.
