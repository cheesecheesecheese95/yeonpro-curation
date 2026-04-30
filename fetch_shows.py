"""연프로 4개 프로그램 YouTube 영상 수집"""
import re, time, json, sqlite3, os
from datetime import datetime, timedelta
from googleapiclient.discovery import build

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yeonpro.db")

# 4대 연프로 — 프로그램별 검색 키워드
SHOWS = {
    "솔로지옥": {
        "icon": "🏝️",
        "color": "#FF6B35",
        "queries": [
            "솔로지옥 리뷰", "솔로지옥 요약", "솔로지옥 결말",
            "솔로지옥 분석", "솔로지옥 몰아보기", "솔로지옥 리캡",
            "솔로지옥5 리뷰", "솔로지옥4 리뷰", "솔로지옥3 리뷰",
            "솔로지옥 커플", "솔로지옥 현커", "singles inferno review",
        ],
    },
    "하트시그널": {
        "icon": "💓",
        "color": "#FF2D55",
        "queries": [
            "하트시그널 리뷰", "하트시그널 요약", "하트시그널 분석",
            "하트시그널 몰아보기", "하트시그널5 리뷰", "하트시그널4 리뷰",
            "하트시그널 커플", "하트시그널 결말", "heart signal review",
            "하트시그널 패널", "하트시그널 떡밥",
        ],
    },
    "나는솔로": {
        "icon": "🌹",
        "color": "#C0392B",
        "queries": [
            "나는솔로 리뷰", "나는솔로 요약", "나는솔로 분석",
            "나는솔로 결말", "나솔 리뷰", "나솔 요약",
            "나는솔로 현커", "나는솔로 라방 요약",
            "나는솔로 영숙 영철", "나는솔로 순삭",
        ],
    },
    "환승연애": {
        "icon": "🔄",
        "color": "#8E44AD",
        "queries": [
            "환승연애 리뷰", "환승연애 요약", "환승연애 분석",
            "환승연애 몰아보기", "환승연애4 리뷰", "환승연애3 리뷰",
            "환승연애 결말", "환승연애 커플", "EXchange review",
            "환승연애 현커", "환승연애 떡밥",
        ],
    },
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY,
        show_name TEXT NOT NULL,
        channel_id TEXT,
        channel_name TEXT,
        title TEXT,
        description TEXT,
        published_at TEXT,
        view_count INTEGER DEFAULT 0,
        like_count INTEGER DEFAULT 0,
        comment_count INTEGER DEFAULT 0,
        duration_sec INTEGER DEFAULT 0,
        thumbnail_url TEXT,
        season TEXT,
        episode TEXT,
        content_type TEXT,
        fetched_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_show ON videos(show_name);
    CREATE INDEX IF NOT EXISTS idx_views ON videos(view_count DESC);
    CREATE INDEX IF NOT EXISTS idx_date ON videos(published_at DESC);
    """)
    conn.commit()
    conn.close()


def parse_duration(iso):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    if not m: return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h*3600 + mi*60 + s


def extract_season(title, show_name):
    """시즌 추출"""
    # 솔로지옥5, 하트시그널4 등
    m = re.search(rf'{show_name}\s*(\d+)', title)
    if m: return f"시즌{m.group(1)}"
    # 시즌 N, S N, 시즌N
    m = re.search(r'시즌\s*(\d+)|[Ss](?:eason)?\s*(\d+)', title)
    if m: return f"시즌{m.group(1) or m.group(2)}"
    # 나는솔로 NN기
    m = re.search(r'(\d+)\s*기', title)
    if m: return f"{m.group(1)}기"
    return None


def extract_episode(title):
    """화차 추출"""
    m = re.search(r'(\d+)\s*화|[Ee][Pp]\.?\s*(\d+)|(\d+)\s*회', title)
    if m: return m.group(1) or m.group(2) or m.group(3)
    return None


def fetch_all(max_per_query=100):
    init_db()
    yt = build("youtube", "v3", developerKey=API_KEY)
    conn = get_conn()
    existing = set(r[0] for r in conn.execute("SELECT video_id FROM videos").fetchall())
    print(f"기존 DB: {len(existing)}개\n")

    total_new = 0
    seen = set()

    for show_name, show_config in SHOWS.items():
        print(f"\n{'='*50}")
        print(f"{show_config['icon']} {show_name}")
        print(f"{'='*50}")
        show_new = 0

        for qi, query in enumerate(show_config["queries"], 1):
            print(f"  [{qi}/{len(show_config['queries'])}] 🔍 '{query}'", end="")
            page_token = None
            batch_new = 0

            for page in range(max_per_query // 50):
                params = {
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": 50,
                    "order": "relevance",
                    "relevanceLanguage": "ko",
                }
                if page_token:
                    params["pageToken"] = page_token

                try:
                    resp = yt.search().list(**params).execute()
                except Exception as e:
                    print(f" ❌ {e}")
                    break

                items = resp.get("items", [])
                if not items: break

                vids = [i["id"]["videoId"] for i in items
                        if i["id"]["videoId"] not in existing and i["id"]["videoId"] not in seen]
                for v in vids: seen.add(v)

                if not vids:
                    page_token = resp.get("nextPageToken")
                    if not page_token: break
                    continue

                detail = yt.videos().list(
                    part="snippet,contentDetails,statistics",
                    id=",".join(vids)
                ).execute()

                for item in detail.get("items", []):
                    dur = parse_duration(item.get("contentDetails", {}).get("duration", ""))
                    if dur < 30: continue  # 30초 미만 제외

                    sn = item["snippet"]
                    stats = item.get("statistics", {})
                    title = sn.get("title", "")
                    desc = (sn.get("description") or "")[:1500]
                    thumb = sn.get("thumbnails", {}).get("high", {}).get("url",
                            sn.get("thumbnails", {}).get("medium", {}).get("url", ""))

                    season = extract_season(title, show_name)
                    episode = extract_episode(title)

                    conn.execute("""
                        INSERT OR IGNORE INTO videos
                        (video_id, show_name, channel_id, channel_name, title, description,
                         published_at, view_count, like_count, comment_count,
                         duration_sec, thumbnail_url, season, episode)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        item["id"], show_name, sn.get("channelId", ""),
                        sn.get("channelTitle", ""), title, desc,
                        sn.get("publishedAt", ""),
                        int(stats.get("viewCount", 0)),
                        int(stats.get("likeCount", 0)),
                        int(stats.get("commentCount", 0)),
                        dur, thumb, season, episode,
                    ))
                    batch_new += 1

                conn.commit()
                page_token = resp.get("nextPageToken")
                if not page_token: break
                time.sleep(0.2)

            show_new += batch_new
            print(f" +{batch_new}")

        total_new += show_new
        print(f"  → {show_name} 소계: {show_new}개")

    conn.close()
    print(f"\n✅ 총 수집: {total_new}개")


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    print("📺 연프로 영상 수집 시작...")
    fetch_all()
