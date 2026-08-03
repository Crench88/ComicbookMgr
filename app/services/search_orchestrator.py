"""Merge, rank, and deduplicate comic search results from multiple sources."""

from concurrent.futures import ThreadPoolExecutor

from . import comicvine, local_catalog, barcode


def _result_dedup_key(result: dict) -> str:
    if result.get('comicvine_id'):
        return f"cv:{result['comicvine_id']}"
    if result.get('id') and str(result.get('source')) == 'Series Catalog':
        return f"local:{result['id']}"
    upc = result.get('upc') or ''
    if upc:
        return f"upc:{upc}"
    return (
        f"{result.get('source', '')}|"
        f"{result.get('series', '')}|"
        f"{result.get('volume_start_year', '')}|"
        f"{result.get('issue_number', '')}|"
        f"{result.get('publisher', '')}"
    ).lower()


def _source_priority(source: str) -> int:
    priorities = {
        'Series Catalog': -25,
        'ComicVine': 0,
        'UPC Database': 2,
        'Barcode Lookup': 2,
    }
    return priorities.get(source or '', 5)


def deduplicate_results(results: list) -> list:
    seen = set()
    unique = []
    for result in results:
        key = _result_dedup_key(result)
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def rank_results(results: list, query: str = '', series_name: str = '',
                 issue_number: str = '') -> list:
    parsed = comicvine.parse_query(
        comicvine.compose_search_query(query, series_name, issue_number)
    )
    parsed_series = (parsed.get('series') or series_name or '').lower()
    parsed_year = parsed.get('year')
    target_issue = comicvine.normalize_issue_number(
        parsed.get('issue') or issue_number or ''
    )

    def score(r):
        s = _source_priority(r.get('source', ''))
        if parsed_series:
            series_low = (r.get('series') or '').lower()
            if parsed_series == series_low:
                s -= 10
            elif parsed_series in series_low:
                s -= 5
        if target_issue:
            if comicvine.normalize_issue_number(r.get('issue_number', '')) == target_issue:
                s -= 8
        start_year = r.get('volume_start_year') or ''
        if parsed_year and start_year == str(parsed_year):
            s -= 6
        return s

    return sorted(results, key=score)


def sanitize_for_json(results: list) -> list:
    out = []
    for issue in results:
        out.append({
            'id': issue.get('id'),
            'comicvine_id': issue.get('comicvine_id'),
            'title': issue.get('title', issue.get('name', '')),
            'issue_title': issue.get('issue_title', ''),
            'series': issue.get('series', ''),
            'issue_number': issue.get('issue_number', ''),
            'publisher': issue.get('publisher', ''),
            'characters': issue.get('characters', ''),
            **{
                field: issue.get(field, '')
                for field in comicvine.CREDIT_FIELD_NAMES
            },
            'teams': issue.get('teams', ''),
            'story_arc': issue.get('story_arc', ''),
            'writers': issue.get('writers', []),
            'artists': issue.get('artists', []),
            'genre': issue.get('genre', 'Comic'),
            'release_date': issue.get('release_date', ''),
            'cover_date': issue.get('cover_date', ''),
            'description': issue.get('description', ''),
            'comicvine_url': issue.get('comicvine_url', ''),
            'cover_image_url': issue.get('cover_image_url', ''),
            'cover_images': issue.get('cover_images', []),
            'volume': issue.get('volume', ''),
            'volume_start_year': issue.get('volume_start_year', ''),
            'upc': issue.get('upc', ''),
            'source': issue.get('source', 'Unknown'),
            'has_variants_endpoint': bool(issue.get('has_variants_endpoint')),
            'series_id': issue.get('series_id'),
        })
    return out


def run_comic_search(*, query='', series_name='', issue_number='',
                     search_comicvine=True, search_local=True,
                     comicvine_api_key='', upc_api_key='', barcode_api_key='',
                     volume_id=None, local_series_id=None,
                     na_publishers_only=True):
    """Run all enabled search sources in parallel and return merged results."""
    effective_query = comicvine.compose_search_query(query, series_name, issue_number)
    upc = barcode.extract_barcode(query) or barcode.extract_barcode(effective_query)

    all_results = []

    if upc:
        # ComicVine has no barcode data, so a UPC only goes to the barcode APIs.
        # When they come up empty we fall through to the normal search below.
        barcode_results = barcode.search_barcode(upc, upc_api_key, barcode_api_key)
        all_results.extend(barcode_results)
        if all_results:
            merged = deduplicate_results(all_results)
            return sanitize_for_json(rank_results(merged, query, series_name, issue_number))

    futures = {}

    def _local():
        if not search_local:
            return []
        return local_catalog.search_local_database(
            query, series_name=series_name, issue_number=issue_number,
            local_series_id=local_series_id,
        )

    def _comicvine():
        if not search_comicvine or not comicvine_api_key:
            return []
        return comicvine.search_comicvine_api(
            query, comicvine_api_key,
            series_name=series_name, issue_number=issue_number,
            volume_id=volume_id,
            na_publishers_only=na_publishers_only,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        if search_local:
            futures['local'] = pool.submit(_local)
        if search_comicvine and comicvine_api_key:
            futures['cv'] = pool.submit(_comicvine)

        for fut in futures.values():
            try:
                all_results.extend(fut.result())
            except Exception:
                pass

    merged = deduplicate_results(all_results)
    ranked = rank_results(merged, query, series_name, issue_number)
    return sanitize_for_json(ranked[:comicvine.MAX_SEARCH_RESULTS + 10])
