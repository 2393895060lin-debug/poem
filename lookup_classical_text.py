from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

GAOKAO_URL = "https://raw.githubusercontent.com/clover-yan/gaokao-poetry/master/sentences.json"
POETRY_SEARCH_URL = "https://poetry.palemoky.com/api/search"
CACHE_MAX_AGE = timedelta(days=14)
USER_AGENT = "Codex poem deploy/1.0"

LOCAL_TEXT_LIBRARY = [
    {
        "title": "岳阳楼记",
        "author": "范仲淹",
        "dynasty": "北宋",
        "source": "内置古文库",
        "content": [
            "庆历四年春，滕子京谪守巴陵郡。越明年，政通人和，百废具兴。乃重修岳阳楼，增其旧制，刻唐贤今人诗赋于其上。属予作文以记之。",
            "予观夫巴陵胜状，在洞庭一湖。衔远山，吞长江，浩浩汤汤，横无际涯；朝晖夕阴，气象万千。此则岳阳楼之大观也，前人之述备矣。然则北通巫峡，南极潇湘，迁客骚人，多会于此，览物之情，得无异乎？",
            "若夫淫雨霏霏，连月不开，阴风怒号，浊浪排空；日星隐曜，山岳潜形；商旅不行，樯倾楫摧；薄暮冥冥，虎啸猿啼。登斯楼也，则有去国怀乡，忧谗畏讥，满目萧然，感极而悲者矣。",
            "至若春和景明，波澜不惊，上下天光，一碧万顷；沙鸥翔集，锦鳞游泳；岸芷汀兰，郁郁青青。而或长烟一空，皓月千里，浮光跃金，静影沉璧；渔歌互答，此乐何极。登斯楼也，则有心旷神怡，宠辱偕忘，把酒临风，其喜洋洋者矣。",
            "嗟夫！予尝求古仁人之心，或异二者之为，何哉？不以物喜，不以己悲；居庙堂之高，则忧其民；处江湖之远，则忧其君。是进亦忧，退亦忧。然则何时而乐耶？其必曰“先天下之忧而忧，后天下之乐而乐”乎！噫！微斯人，吾谁与归？",
            "时六年九月十五日。",
        ],
    },
    {
        "title": "桃花源记",
        "author": "陶渊明",
        "dynasty": "东晋",
        "source": "内置古文库",
        "content": [
            "晋太元中，武陵人捕鱼为业。缘溪行，忘路之远近。",
            "忽逢桃花林，夹岸数百步，中无杂树，芳草鲜美，落英缤纷。渔人甚异之。复前行，欲穷其林。",
            "林尽水源，便得一山，山有小口，仿佛若有光。便舍船，从口入。",
            "初极狭，才通人。复行数十步，豁然开朗。土地平旷，屋舍俨然，有良田、美池、桑竹之属。阡陌交通，鸡犬相闻。其中往来种作，男女衣着，悉如外人。黄发垂髫，并怡然自乐。",
            "见渔人，乃大惊，问所从来。具答之。便要还家，设酒杀鸡作食。村中闻有此人，咸来问讯。自云先世避秦时乱，率妻子邑人来此绝境，不复出焉，遂与外人间隔。问今是何世，乃不知有汉，无论魏晋。此人一一为具言所闻，皆叹惋。",
            "余人各复延至其家，皆出酒食。停数日，辞去。此中人语云：“不足为外人道也。”",
            "既出，得其船，便扶向路，处处志之。及郡下，诣太守，说如此。太守即遣人随其往，寻向所志，遂迷，不复得路。",
            "南阳刘子骥，高尚士也，闻之，欣然规往。未果，寻病终。后遂无问津者。",
        ],
    },
    {
        "title": "陋室铭",
        "author": "刘禹锡",
        "dynasty": "唐",
        "source": "内置古文库",
        "content": [
            "山不在高，有仙则名。水不在深，有龙则灵。",
            "斯是陋室，惟吾德馨。",
            "苔痕上阶绿，草色入帘青。",
            "谈笑有鸿儒，往来无白丁。",
            "可以调素琴，阅金经。无丝竹之乱耳，无案牍之劳形。",
            "南阳诸葛庐，西蜀子云亭。",
            "孔子云：何陋之有？",
        ],
    },
    {
        "title": "满江红",
        "author": "岳飞",
        "dynasty": "南宋",
        "source": "内置古文库",
        "content": [
            "怒发冲冠，凭栏处、潇潇雨歇。",
            "抬望眼，仰天长啸，壮怀激烈。",
            "三十功名尘与土，八千里路云和月。",
            "莫等闲、白了少年头，空悲切。",
            "靖康耻，犹未雪；臣子恨，何时灭！",
            "驾长车，踏破贺兰山缺。",
            "壮志饥餐胡虏肉，笑谈渴饮匈奴血。",
            "待从头、收拾旧山河，朝天阙。",
        ],
    },
]


@dataclass
class LookupResult:
    title: str
    author: str
    content: list[str]
    source: str
    dynasty: str = ""


def normalize(text: str) -> str:
    stripped = re.sub(r"[\s\u3000《》〈〉「」『』【】()（）]", "", text or "")
    return stripped.casefold()


def author_matches(candidate_author: str, requested_author: str) -> bool:
    if not requested_author:
        return True
    return normalize(requested_author) in normalize(candidate_author)


def score_title(candidate_title: str, requested_title: str) -> int:
    return 100 if normalize(candidate_title) == normalize(requested_title) else 0


def cache_dir() -> Path:
    configured = os.getenv("POEM_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / "cache" / "lookup"
    root = os.getenv("XDG_CACHE_HOME", "").strip()
    if root:
        return Path(root) / "poem-site"
    return Path.home() / ".cache" / "poem-site"


def fetch_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_gaokao_dataset() -> list[dict]:
    target = cache_dir() / "gaokao-poetry.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        mtime = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
        if datetime.now(timezone.utc) - mtime <= CACHE_MAX_AGE:
            return json.loads(target.read_text(encoding="utf-8"))

    try:
        payload = fetch_json(GAOKAO_URL)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload  # type: ignore[return-value]
    except Exception:
        if target.exists():
            return json.loads(target.read_text(encoding="utf-8"))
        raise


def search_local_library(title: str, author: str) -> LookupResult | None:
    best_entry = None
    best_score = 0
    for entry in LOCAL_TEXT_LIBRARY:
        if not author_matches(entry.get("author", ""), author):
            continue
        score = score_title(entry.get("title", ""), title)
        if score > best_score:
            best_entry = entry
            best_score = score

    if not best_entry or best_score < 100:
        return None

    return LookupResult(
        title=best_entry["title"],
        author=best_entry.get("author", ""),
        dynasty=best_entry.get("dynasty", ""),
        content=best_entry.get("content", []),
        source=best_entry.get("source", "内置古文库"),
    )


def search_gaokao(title: str, author: str) -> LookupResult | None:
    best_entry = None
    best_score = 0
    for entry in load_gaokao_dataset():
        if not author_matches(entry.get("author", ""), author):
            continue
        score = score_title(entry.get("title", ""), title)
        if score > best_score:
            best_entry = entry
            best_score = score

    if not best_entry or best_score < 100:
        return None

    return LookupResult(
        title=best_entry["title"],
        author=best_entry.get("author", ""),
        content=best_entry.get("content", []),
        source="gaokao-poetry 补充古文库",
    )


def search_poetry_api(title: str, author: str) -> LookupResult | None:
    if len(normalize(title)) < 3:
        return None

    params = urllib.parse.urlencode(
        {"q": title, "type": "title", "page": 1, "pageSize": 20},
        quote_via=urllib.parse.quote,
    )
    payload = fetch_json(f"{POETRY_SEARCH_URL}?{params}")
    if not isinstance(payload, dict):
        return None

    best_entry = None
    best_score = 0
    for entry in payload.get("data", []):
        entry_title = entry.get("title", "")
        entry_author = ((entry.get("author") or {}).get("name")) or ""
        if not author_matches(entry_author, author):
            continue
        score = score_title(entry_title, title)
        if score > best_score:
            best_entry = entry
            best_score = score

    if not best_entry or best_score < 100:
        return None

    return LookupResult(
        title=best_entry.get("title", title),
        author=((best_entry.get("author") or {}).get("name")) or "",
        dynasty=((best_entry.get("dynasty") or {}).get("name")) or "",
        content=best_entry.get("content", []),
        source="诗泉 API（基于 chinese-poetry）",
    )


def lookup(title: str, author: str = "") -> LookupResult:
    errors = []

    try:
        result = search_local_library(title, author)
        if result:
            return result
    except Exception as exc:
        errors.append(f"内置古文库：{exc}")

    try:
        result = search_gaokao(title, author)
        if result:
            return result
    except Exception as exc:
        errors.append(f"补充古文库：{exc}")

    try:
        result = search_poetry_api(title, author)
        if result:
            return result
    except Exception as exc:
        errors.append(f"诗词 API：{exc}")

    detail = ""
    if errors:
        detail = "\n数据源状态：\n- " + "\n- ".join(errors)

    if author:
        raise LookupError(f"未找到作者为“{author}”的《{title}》。{detail}")
    raise LookupError(f"未找到《{title}》的全文。{detail}")
