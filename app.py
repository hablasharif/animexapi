import re, json, urllib.request, urllib.parse
import streamlit as st

SITE = "https://animex.one"
API  = "https://pp.animex.one/rest/api"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Origin": SITE, "Referer": f"{SITE}/", "Accept": "*/*"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()

def find_anime_id_via_search(anilist_id):
    """
    Search animex.one for the anime, find a watch link that contains our anilist_id,
    then scrape that page to get the internal animeId.
    """
    # 1. Hit the site's search API
    search_url = f"{API}/search?query=&anilistId={anilist_id}"
    try:
        results = json.loads(fetch(search_url))
        if isinstance(results, list) and results:
            for r in results:
                aid = r.get("id") or r.get("animeId") or r.get("anime_id")
                if aid:
                    return str(aid), None
        if isinstance(results, dict):
            aid = results.get("id") or results.get("animeId")
            if aid:
                return str(aid), None
    except Exception:
        pass

    # 2. Try the browse/filter endpoint some sites expose
    for endpoint in [
        f"{API}/anime?anilistId={anilist_id}",
        f"{API}/info/{anilist_id}",
        f"{API}/anime/{anilist_id}",
    ]:
        try:
            data = json.loads(fetch(endpoint))
            if isinstance(data, dict):
                aid = data.get("id") or data.get("animeId") or data.get("anime_id")
                if aid:
                    return str(aid), None
        except Exception:
            continue

    # 3. Scrape the site's own search page for a watch link containing our anilist_id
    try:
        q = urllib.parse.quote(str(anilist_id))
        search_page = fetch(f"{SITE}/search?q={q}").decode("utf-8", errors="replace")
        # Look for any href like /watch/some-slug-<anilist_id>-episode-N
        pattern = rf'/watch/([^"\']+?-{re.escape(str(anilist_id))}-episode-\d+)'
        m = re.search(pattern, search_page)
        if m:
            watch_path = m.group(0)
            watch_url = f"{SITE}{watch_path}"
            return _scrape_anime_id_from_watch(watch_url, anilist_id)
    except Exception:
        pass

    return None, (
        "Could not auto-discover the anime. "
        "Please paste the full animex.one watch URL below instead."
    )

def _scrape_anime_id_from_watch(watch_url, anilist_id):
    """Scrape the internal animeId from a watch page."""
    try:
        html = fetch(watch_url).decode("utf-8", errors="replace")
        aid_m = (
            re.search(rf"animeId\s*:\s*['\"]([^'\"]+)['\"].{{0,300}}?anilistId\s*:\s*{anilist_id}\b", html)
            or re.search(rf"anilistId\s*:\s*{anilist_id}\b.{{0,300}}?animeId\s*:\s*['\"]([^'\"]+)['\"]", html)
            or re.search(r'animeId\s*:\s*[\'"]([^\'"]+)[\'"]', html)
        )
        if aid_m:
            return aid_m.group(1), None
        return None, "Found watch page but could not extract internal animeId."
    except Exception as e:
        return None, f"Failed to scrape watch page: {e}"

def resolve_from_watch_url(watch_url):
    """Original URL-based resolver (fallback)."""
    m = re.search(r"/watch/.+-(\d+)-episode-(\d+)", watch_url)
    if not m:
        return None, None, None, "Invalid URL format — expected /watch/<slug>-<id>-episode-<ep>"
    anilist_id, episode = m.group(1), m.group(2)
    anime_id, error = _scrape_anime_id_from_watch(watch_url, anilist_id)
    if error:
        return None, None, None, error
    streams, err = _fetch_streams(anime_id, episode)
    return anime_id, anilist_id, episode, err or None

def _fetch_streams(anime_id, episode):
    try:
        servers = json.loads(fetch(f"{API}/servers?id={anime_id}&epNum={episode}"))
    except Exception as e:
        return None, f"Failed to fetch server list: {e}"

    streams = []
    for typ, key in (("sub", "subProviders"), ("dub", "dubProviders")):
        for p in servers.get(key, []):
            try:
                data = json.loads(fetch(
                    f"{API}/sources?id={anime_id}&epNum={episode}&type={typ}&providerId={p['id']}"
                ))
                for s in data.get("sources", []):
                    streams.append({
                        "type": typ,
                        "provider": p["id"],
                        "url": s["url"],
                        "quality": s.get("quality", "auto"),
                        "mimetype": s.get("type", "")
                    })
            except Exception as e:
                streams.append({"type": typ, "provider": p["id"], "error": str(e)})
    return streams, None

def resolve(anilist_id, episode):
    anime_id, error = find_anime_id_via_search(anilist_id)
    if error:
        return None, None, error
    streams, err = _fetch_streams(anime_id, episode)
    return anime_id, streams, err

# ── Streamlit UI ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="AnimeX Stream Resolver", page_icon="🎬", layout="wide")
st.title("🎬 AnimeX Stream Resolver")

mode = st.radio("Input mode", ["AniList ID + Episode", "Full watch URL"], horizontal=True)
st.divider()

if mode == "AniList ID + Episode":
    col1, col2 = st.columns([2, 1])
    with col1:
        anilist_id = st.text_input("AniList ID", placeholder="e.g. 1735")
    with col2:
        episode = st.text_input("Episode", placeholder="e.g. 3")
    run = st.button("Resolve Streams", type="primary")

    if run:
        if not anilist_id or not episode:
            st.warning("Please fill in both fields.")
        else:
            with st.spinner("Searching for anime…"):
                anime_id, streams, error = resolve(anilist_id.strip(), episode.strip())
else:
    watch_url = st.text_input(
        "Watch URL",
        placeholder="https://animex.one/watch/naruto-shippuden-1735-episode-3"
    )
    run = st.button("Resolve Streams", type="primary")

    if run:
        if not watch_url:
            st.warning("Please enter a watch URL.")
        else:
            with st.spinner("Resolving…"):
                anime_id, anilist_id, episode, error = resolve_from_watch_url(watch_url.strip())
                streams = None
                if not error:
                    streams, error = _fetch_streams(anime_id, episode)

# ── Results ───────────────────────────────────────────────────────────────────
if 'run' in dir() and run:
    if 'error' in dir() and error:
        st.error(error)
        if "auto-discover" in str(error):
            st.info("Switch to **Full watch URL** mode above and paste the URL from animex.one directly.")
    elif streams is not None:
        st.success(f"✅ Internal ID: `{anime_id}`  —  {len(streams)} stream(s) found")

        with st.expander("📦 Raw JSON", expanded=True):
            st.json(streams)

        st.divider()
        sub_streams = [s for s in streams if s.get("type") == "sub"]
        dub_streams = [s for s in streams if s.get("type") == "dub"]
        c1, c2 = st.columns(2)
        for col, group, label in ((c1, sub_streams, "🔤 SUB"), (c2, dub_streams, "🔊 DUB")):
            with col:
                st.subheader(label)
                if not group:
                    st.caption("None found")
                for s in group:
                    with st.container(border=True):
                        if "error" in s:
                            st.error(f"**{s['provider']}** — {s['error']}")
                        else:
                            st.markdown(f"**Provider:** `{s['provider']}`")
                            st.markdown(f"**Quality:** `{s['quality']}`")
                            st.markdown(f"**Type:** `{s['mimetype']}`")
                            st.code(s["url"], language=None)