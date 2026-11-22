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
