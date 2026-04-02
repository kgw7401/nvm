[English](README.md) | **한국어**

# NVM (Non-Volatile Memory)

> 당신의 엔지니어링 사고, 보존합니다.

NVM은 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 플러그인으로, Claude 대화 로그와 git 히스토리를 분석하여 **사고 궤적 문서**를 자동 생성합니다.

코드는 남지만, 그 뒤의 사고 과정은 휘발됩니다. NVM은 *왜 이렇게 풀었는가*를 사라지기 전에 잡아냅니다.

## What It Does

코딩 세션 후 `/nvm`을 실행하면:

1. 해당 기간의 Claude 대화 로그 + git 커밋을 **분석**
2. 사람의 문제 정의 과정과 Claude의 문제 해결 접근을 **추출**
3. `.nvm/{date}.md`에 서사형 문서를 **생성**

단순 요약이나 로그가 아닙니다 — **사고 과정의 서사적 복원**입니다.

## Example

```markdown
## event-hub: Amplitude API 안정화 — shared session + circuit breaker + fire-and-forget

**Problem**
Airflow pod에서 aiohttp `CancelledError`가 연속 발생하며 Amplitude 이벤트 전송이
전량 실패. 근본 원인은 매 요청마다 `ClientSession`을 새로 생성해 커넥션 풀이
고갈되는 구조였음.

**Trajectory**
1. 매 요청마다 세션 생성 → 앱 수준 싱글턴으로 교체 (lifespan에서 open/close)
2. tenacity retry 제거 → 재시도가 풀 고갈을 악화시킴; fire-and-forget으로 전환
3. Circuit breaker 설계 논쟁:

> **나:** "그래도 amplitude에 이벤트가 전송 안되는건 좀 크리티컬 해서 말이야"
> **Claude:** "PubSub에 모든 이벤트가 들어가므로, Amplitude 쪽은 나중에 복구 가능합니다"

합의: circuit open = 건너뛰지 않고 단축 timeout(5s)으로 여전히 시도.

**Resolution**
exception handler를 등록하여 uncaught exception을 포착하도록 했다.
이후 fire-and-forget 전환으로 메인 스레드 블로킹을 제거했다.
```

## Installation

### From GitHub (standalone marketplace)

```
/plugin marketplace add https://github.com/kgw7401/nvm.git

/plugin install nvm
```

### Manual Installation

```bash
git clone https://github.com/kgw7401/nvm.git
cp -r nvm/skills/nvm ~/.claude/commands/
cp -r nvm/scripts ~/your-project/scripts/
```

## Usage

```
/nvm              # 오늘의 사고 궤적
/nvm week         # 최근 7일
/nvm 2026-03-25   # 특정 날짜부터 현재까지
```

결과물은 프로젝트 디렉토리의 `.nvm/{date}.md`에 저장됩니다.

## How It Works

```
/nvm [period]
  │
  ├─ 1. 기간 파싱 (today / week / YYYY-MM-DD)
  │
  ├─ 2. extract_session.py로 세션 JSONL 전처리
  │     (원본 530KB → ~25K 토큰 — 유저 메시지 전량 보존 + Claude 응답 200자 축약)
  │
  ├─ 3. git log + 커밋 상세 수집
  │
  ├─ 4. 서사형 문서 생성
  │     • 사람의 축: 문제 정의, 방향 설정, 의사결정
  │     • Claude의 축: 접근 방식, 대안 검토, 구현 선택
  │
  └─ 5. .nvm/{date}.md 저장
```

### Generation Principles

- **자유 서사** — 고정 필드가 아닌, 내용에 맞게 유연하게 구성 (의사결정, 디버깅, 학습 등)
- **필수 3요소** — 카드마다: 한 줄 요약, 핵심 내용, 참고 자료 링크
- **카드 깊이 가변** — 의사결정 + 소거 과정이 있으면 깊게, 단순 수정이면 얕게
- **대화 발췌** — 유저가 방향을 전환한 전환점을 포착
- **언어 자동 감지** — 대화에서 사용한 언어로 문서 생성

## Project Structure

```
nvm/
├── .claude-plugin/
│   └── plugin.json          # 플러그인 메타데이터
├── skills/
│   └── nvm/
│       └── SKILL.md         # /nvm 커맨드 정의
├── scripts/
│   └── extract_session.py   # JSONL 전처리기
├── LICENSE
└── README.md
```

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.10+
- git

외부 Python 패키지 의존성 없음 — 표준 라이브러리만 사용합니다.

## Why NVM?

| 기존 도구 | NVM |
|----------|-----|
| 로그 저장 | 사고 과정 복원 |
| 요약 제공 | 서사 생성 |
| 고정 포맷 | 내용에 맞게 적응 |
| 무슨 일이 있었는지 기록 | **왜 그렇게 풀었는지** 포착 |

"Non-Volatile Memory"라는 이름은 핵심 아이디어를 반영합니다: 하드웨어의 NVM이 전원이 꺼져도 데이터를 보존하듯, 엔지니어의 사고 과정을 영속적으로 만듭니다.

## Contributing

기여를 환영합니다! 이슈를 열거나 PR을 보내주세요.

## License

[MIT](LICENSE)
