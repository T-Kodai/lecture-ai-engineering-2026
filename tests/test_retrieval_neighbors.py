"""第5回 宿題（実装）: 検索結果に前後ページを足す処理のテスト。APIは呼ばない。"""

from app import retrieval


def page(doc: str, n: int) -> dict:
    return {"page_id": f"{doc}-p{n:03d}", "document_id": doc, "page": n, "content": f"{doc} の {n} ページ"}


PAGES = [page("lec01-main", n) for n in (1, 2, 3, 4)] + [page("lec02-main", n) for n in (1, 2, 3)]


def ids(results: list[dict]) -> list[str]:
    return [r["page_id"] for r in results]


def test_window_zero_returns_hits_unchanged():
    hits = [{**page("lec01-main", 2), "distance": 0.1}]
    assert retrieval.add_neighbor_pages(hits, PAGES, 0) is hits


def test_neighbors_are_added_around_each_hit_in_reading_order():
    hits = [{**page("lec01-main", 2), "distance": 0.1}]
    results = retrieval.add_neighbor_pages(hits, PAGES, 1)
    assert ids(results) == ["lec01-main-p001", "lec01-main-p002", "lec01-main-p003"]
    assert results[1]["distance"] == 0.1 and "neighbor_of" not in results[1]
    assert results[0]["neighbor_of"] == results[2]["neighbor_of"] == "lec01-main-p002"
    assert (results[0]["offset"], results[2]["offset"]) == (-1, 1)


def test_neighbors_do_not_cross_documents():
    # lec01 の最後のページの次に、lec02 の最初のページを足さない
    hits = [{**page("lec01-main", 4), "distance": 0.1}, {**page("lec02-main", 1), "distance": 0.2}]
    results = retrieval.add_neighbor_pages(hits, PAGES, 1)
    assert ids(results) == ["lec01-main-p003", "lec01-main-p004", "lec02-main-p001", "lec02-main-p002"]
    assert results[2]["distance"] == 0.2 and "neighbor_of" not in results[2]


def test_pages_are_not_duplicated_and_hits_keep_their_score():
    # 隣り合う 2 ページが両方当たったときは、どちらも当たった側として 1 回ずつだけ入る
    hits = [{**page("lec01-main", 2), "distance": 0.1}, {**page("lec01-main", 3), "distance": 0.2}]
    results = retrieval.add_neighbor_pages(hits, PAGES, 1)
    assert ids(results) == ["lec01-main-p001", "lec01-main-p002", "lec01-main-p003", "lec01-main-p004"]
    assert len(set(ids(results))) == len(results)
    assert [r.get("distance") for r in results] == [None, 0.1, 0.2, None]


def test_hit_outside_loaded_pages_is_kept_without_neighbors():
    hits = [{**page("lec09-main", 5), "distance": 0.1}]
    assert ids(retrieval.add_neighbor_pages(hits, PAGES, 1)) == ["lec09-main-p005"]


def test_page_between_two_hits_is_added_once_for_the_higher_ranked_hit():
    # p.1 と p.3 が当たると、間の p.2 は先に処理した（順位が上の）p.3 の前後として 1 回だけ入る
    hits = [{**page("lec01-main", 3), "distance": 0.1}, {**page("lec01-main", 1), "distance": 0.2}]
    results = retrieval.add_neighbor_pages(hits, PAGES, 1)
    assert ids(results) == ["lec01-main-p002", "lec01-main-p003", "lec01-main-p004", "lec01-main-p001"]
    assert results[0]["neighbor_of"] == "lec01-main-p003"


def test_search_returns_vector_hits_unchanged_when_neighbors_is_zero(monkeypatch):
    hits = [{**page("lec01-main", 2), "distance": 0.1}]
    monkeypatch.setattr(retrieval, "search_vector", lambda query: hits)
    monkeypatch.setattr(retrieval, "RAG_NEIGHBOR_PAGES", 0)
    assert retrieval.search("質問") is hits


def test_search_takes_neighbors_from_the_index_pages(monkeypatch):
    # 前後ページは、検索に使った索引のページ一覧（load_index_pages）から取る
    hits = [{**page("lec01-main", 2), "distance": 0.1}]
    monkeypatch.setattr(retrieval, "search_vector", lambda query: hits)
    monkeypatch.setattr(retrieval, "load_index_pages", lambda path=None: PAGES)
    monkeypatch.setattr(retrieval, "RAG_NEIGHBOR_PAGES", 1)
    assert ids(retrieval.search("質問")) == ["lec01-main-p001", "lec01-main-p002", "lec01-main-p003"]


def test_graph_search_is_not_changed_by_the_neighbors_setting(monkeypatch):
    # Graph の入口は search_vector を使うので、前後ページの設定で結果が変わらない（同梱の教材 JSON・graph.json を使う）
    pages = {p["page_id"]: p for p in retrieval.load_pages()}
    seeds = [{**pages[pid], "distance": d} for pid, d in
             [("lec02-main-p052", 0.1), ("lec02-main-p051", 0.2), ("lec02-main-p060", 0.3)]]
    monkeypatch.setattr(retrieval, "search_vector", lambda query: seeds)
    monkeypatch.setattr(retrieval, "RAG_NEIGHBOR_PAGES", 0)
    before = retrieval.search_graph("質問")
    monkeypatch.setattr(retrieval, "RAG_NEIGHBOR_PAGES", 1)
    assert retrieval.search_graph("質問") == before
    assert [s["page_id"] for s in before["seeds"]] == [s["page_id"] for s in seeds]
