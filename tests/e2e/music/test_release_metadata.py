import asyncio

import pytest
from httpx import AsyncClient  # Для тайп-хинтинга фикстуры

# Импортируем вспомогательные функции
from tests.e2e.helpers import create_metadata_task, get_task_result


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc01_successful_us_market(api_client: AsyncClient):
    """TC01: Successful scenario (US market)."""
    payload = {
        "band_name": "Metallica",
        "release_name": "Master of Puppets",
        "country_code": "US",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC01"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC01) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", f"Task (TC01) status was not SUCCESS. Response: {final_response}"

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC01"

    # Проверки полей согласно TC01
    assert result.get("artist") is not None, "Artist field is missing for TC01"
    assert result["artist"].get("name") == "Metallica", "Artist name mismatch for TC01"

    assert "Master of Puppets" in result.get("release", ""), "Release name mismatch or missing for TC01"

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC01, got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC01"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC01"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC01"
    has_spotify_id = bool(artist_source_ids.get("spotify_artist_id"))
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_spotify_id or has_musicbrainz_id, (
        "Artist source_specific_ids does not contain Spotify or MusicBrainz ID for TC01"
    )

    for track in tracks:
        assert "title" in track, f"Track missing title for TC01: {track}"
        assert "isrc" in track, f"Track missing ISRC for TC01: {track.get('title')}"
        track_source_ids = track.get("source_specific_ids")
        if track_source_ids:
            assert "spotify_track_id" in track_source_ids, (
                f"Track missing spotify_track_id in source_specific_ids for TC01: {track.get('title')}"
            )

    assert result.get("social_links", {}) is not None, "Social links field issue for TC01"
    assert result.get("genre", "") is not None, "Genre field issue for TC01"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc02_successful_gb_market(api_client: AsyncClient):
    """TC02: Successful scenario (GB market)."""
    payload = {
        "band_name": "Iron Maiden",
        "release_name": "The Number of the Beast",
        "country_code": "GB",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC02"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC02) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", f"Task (TC02) status was not SUCCESS. Response: {final_response}"

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC02"

    # Проверки полей согласно TC02 (аналогично TC01, но с другими данными)
    assert result.get("artist") is not None, "Artist field is missing for TC02"
    # Имя артиста может немного отличаться в разных источниках/регионах,
    # но должно содержать ключевое название
    assert "Iron Maiden" in result["artist"].get("name", ""), "Artist name mismatch for TC02"

    assert "The Number of the Beast" in result.get("release", ""), "Release name mismatch or missing for TC02"

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC02, got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC02"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC02"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC02"
    has_spotify_id = bool(artist_source_ids.get("spotify_artist_id"))
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_spotify_id or has_musicbrainz_id, (
        "Artist source_specific_ids does not contain Spotify or MusicBrainz ID for TC02"
    )

    for track in tracks:
        assert "title" in track, f"Track missing title for TC02: {track}"
        assert "isrc" in track, f"Track missing ISRC for TC02: {track.get('title')}"
        track_source_ids = track.get("source_specific_ids")
        if track_source_ids:
            assert "spotify_track_id" in track_source_ids, (
                f"Track missing spotify_track_id in source_specific_ids for TC02: {track.get('title')}"
            )

    assert result.get("social_links", {}) is not None, "Social links field issue for TC02"
    assert result.get("genre", "") is not None, "Genre field issue for TC02"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc03_successful_no_country_pink_floyd(api_client: AsyncClient):
    """TC03 Part 1: Successful scenario (No country_code) - Pink Floyd."""
    payload = {
        "band_name": "Pink Floyd",
        "release_name": "The Dark Side of the Moon",
        # country_code отсутствует
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC03 (Pink Floyd)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC03 Pink Floyd) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC03 Pink Floyd) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC03 (Pink Floyd)"

    # Основные проверки, аналогичные TC01/TC02
    assert result.get("artist") is not None, "Artist field is missing for TC03 (Pink Floyd)"
    assert "Pink Floyd" in result["artist"].get("name", ""), "Artist name mismatch for TC03 (Pink Floyd)"
    assert "The Dark Side of the Moon" in result.get("release", ""), (
        "Release name mismatch or missing for TC03 (Pink Floyd)"
    )

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC03 (Pink Floyd), got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC03 (Pink Floyd)"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC03 (Pink Floyd)"
    # Для запроса без страны, Spotify ID может быть, а может и не быть (зависит от того, как Spotify ищет глобально)
    # MusicBrainz ID более вероятно будет найден
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_musicbrainz_id, "MusicBrainz ID for artist is expected for TC03 (Pink Floyd)"

    # Проверка, что social_links корректно подгружаются (согласно описанию TC03)
    social_links = result.get("social_links")
    assert social_links is not None, "Social links are missing for TC03 (Pink Floyd)"
    # Можно добавить более детальную проверку структуры social_links, если необходимо
    # Например, что это словарь и содержит ожидаемые ключи, если они известны
    assert isinstance(social_links, dict), "Social links should be a dictionary for TC03 (Pink Floyd)"
    # Ожидаем, что какие-то ссылки будут, если они есть для Pink Floyd
    # Эта проверка может быть хрупкой, если у Pink Floyd вдруг пропадут все соц. ссылки
    # TC03 говорит "должны корректно подгружаться и кешироваться"
    # Для первой части достаточно проверить, что они подгрузились (не None и являются словарем)

    assert result.get("genre", "") is not None, "Genre field issue for TC03 (Pink Floyd)"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc03_caching_social_links_metallica(api_client: AsyncClient):
    """TC03 Part 2: Verify caching of social_links for Metallica."""
    band_name = "Metallica"
    release_name = "Load"

    # 1. Первый запрос с country_code
    payload_with_country = {
        "band_name": band_name,
        "release_name": release_name,
        "country_code": "US",
    }
    task_id_1 = await create_metadata_task(api_client, payload_with_country)
    assert task_id_1 is not None, "Failed to create task for TC03 (Metallica, with country)"

    final_response_1 = await get_task_result(api_client, task_id_1)
    assert final_response_1 is not None, (
        f"Task {task_id_1} (TC03 Metallica, with country) did not complete or fetching status failed."
    )
    assert final_response_1.get("status") == "SUCCESS", (
        f"Task (TC03 Metallica, with country) status was not SUCCESS. Response: {final_response_1}"
    )

    result_1 = final_response_1.get("result")
    assert result_1 is not None, "Result is missing for TC03 (Metallica, with country)"

    social_links_1 = result_1.get("social_links")
    assert social_links_1 is not None, "Social links are missing for TC03 (Metallica, with country)"
    assert isinstance(social_links_1, dict), "Social links should be a dict for TC03 (Metallica, with country)"
    # Желательно, чтобы какие-то ссылки были, но главное - что они есть для сравнения
    # print(f"Social links from first request (Metallica with country): {social_links_1}") # Для отладки

    # Небольшая пауза, чтобы гарантировать, что следующая задача, если она создается, будет новой,
    # хотя для кеширования это не должно иметь значения, если task_id разные.
    # Важнее, чтобы данные успели попасть в кеш Redis.
    await asyncio.sleep(1)  # Опциональная небольшая задержка

    # 2. Второй запрос без country_code
    payload_without_country = {
        "band_name": band_name,
        "release_name": release_name,
        # country_code отсутствует
    }
    task_id_2 = await create_metadata_task(api_client, payload_without_country)
    assert task_id_2 is not None, "Failed to create task for TC03 (Metallica, no country)"

    final_response_2 = await get_task_result(api_client, task_id_2)
    assert final_response_2 is not None, (
        f"Task {task_id_2} (TC03 Metallica, no country) did not complete or fetching status failed."
    )
    assert final_response_2.get("status") == "SUCCESS", (
        f"Task (TC03 Metallica, no country) status was not SUCCESS. Response: {final_response_2}"
    )

    result_2 = final_response_2.get("result")
    assert result_2 is not None, "Result is missing for TC03 (Metallica, no country)"

    social_links_2 = result_2.get("social_links")
    assert social_links_2 is not None, "Social links are missing for TC03 (Metallica, no country)"
    assert isinstance(social_links_2, dict), "Social links should be a dict for TC03 (Metallica, no country)"
    # print(f"Social links from second request (Metallica no country): {social_links_2}") # Для отладки

    # 3. Сравнение social_links
    # Они должны быть идентичны, если кеширование работает для артиста
    assert social_links_1 == social_links_2, (
        f"Social links mismatch for TC03 (Metallica). With country: {social_links_1}, No country: {social_links_2}"
    )

    # Дополнительно, убедимся, что и там и там есть какие-то данные, если они вообще существуют для Metallica
    # Эта проверка опциональна и зависит от того, есть ли у Metallica social_links
    if not social_links_1 and not social_links_2:
        print(
            "Warning TC03 (Metallica Caching): No social links found for Metallica in either request. "
            "Caching test for identity still valid if both are consistently empty/None.",
        )
    elif not social_links_1 or not social_links_2:
        # Эта ситуация будет поймана assert social_links_1 == social_links_2, если один None, а другой - нет.
        pass


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc04_artist_with_special_chars(api_client: AsyncClient):
    """TC04: Artist with special characters (e.g., diacritics)."""
    payload = {
        "band_name": "Motörhead",
        "release_name": "Ace of Spades",
        # country_code можно опустить, т.к. главное - проверка имени артиста
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC04 (Motörhead)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC04 Motörhead) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC04 Motörhead) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC04 (Motörhead)"

    assert result.get("artist") is not None, "Artist field is missing for TC04 (Motörhead)"

    # Ключевая проверка: имя артиста должно корректно отображаться
    artist_name = result["artist"].get("name")
    assert artist_name == "Motörhead", f"Artist name mismatch for TC04. Expected 'Motörhead', got '{artist_name}'"

    # Остальные проверки можно сделать аналогично предыдущим тестам для полноты
    assert "Ace of Spades" in result.get("release", ""), "Release name mismatch or missing for TC04 (Motörhead)"

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC04 (Motörhead), got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC04 (Motörhead)"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC04 (Motörhead)"
    # Ожидаем хотя бы MusicBrainz ID
    assert bool(artist_source_ids.get("musicbrainz_artist_id")), (
        "MusicBrainz ID for artist is expected for TC04 (Motörhead)"
    )


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc05_release_with_special_chars(api_client: AsyncClient):
    """TC05: Release with special characters (e.g., apostrophe)."""
    payload = {
        "band_name": "The Who",
        "release_name": "Who's Next",
        # country_code можно опустить
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC05 (The Who)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC05 The Who) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC05 The Who) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC05 (The Who)"

    # Ключевые проверки для TC05
    assert result.get("artist") is not None, "Artist field is missing for TC05 (The Who)"
    artist_name = result["artist"].get("name")
    assert artist_name == "The Who", f"Artist name mismatch for TC05. Expected 'The Who', got '{artist_name}'"

    release_name_response = result.get("release")
    # Ожидаем точное совпадение или, по крайней мере, что основная часть корректна
    # Для большей устойчивости можно использовать `in`, если возможны суффиксы типа (Remastered)
    expected_release_name = "Who\u2019s Next"  # Используем \u2019 для типографского апострофа
    assert expected_release_name in release_name_response, (
        f"Release name mismatch for TC05. Expected '{expected_release_name}' to be in '{release_name_response}'"
    )

    # Остальные проверки для полноты
    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC05 (The Who), got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC05 (The Who)"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC05 (The Who)"
    assert bool(artist_source_ids.get("musicbrainz_artist_id")), (
        "MusicBrainz ID for artist is expected for TC05 (The Who)"
    )


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc06_successful_no_country_global_search(api_client: AsyncClient):
    """TC06: Test global search with a potentially multi-versioned release.

    This test sends a request for "Nirvana - MTV Unplugged in New York" without
    a 'country_code'. The essence is to check how the application handles
    such a case, where a well-known release might have multiple versions or
    representations across different data sources globally. The test verifies
    that a consistent and valid metadata response is returned.
    """
    payload = {
        "band_name": "Nirvana",
        "release_name": "MTV Unplugged in New York",
        # country_code is intentionally omitted
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC06 (Nirvana)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC06 Nirvana) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC06 Nirvana) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC06 (Nirvana)"

    # Basic checks similar to previous tests
    assert result.get("artist") is not None, "Artist field is missing for TC06 (Nirvana)"
    assert "Nirvana" in result["artist"].get("name", ""), "Artist name mismatch for TC06 (Nirvana)"

    expected_release_name_part = "MTV Unplugged in New York"
    actual_release_name = result.get("release", "")
    assert expected_release_name_part.lower() in actual_release_name.lower(), (
        f"Release name mismatch for TC06 (Nirvana). Expected '{expected_release_name_part}' (case-insensitive) "
        f"to be in '{actual_release_name}'"
    )

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC06 (Nirvana), got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC06 (Nirvana)"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC06 (Nirvana)"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC06 (Nirvana)"

    # Expect at least one source ID (Spotify or MusicBrainz)
    has_spotify_id = bool(artist_source_ids.get("spotify_artist_id"))
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_spotify_id or has_musicbrainz_id, (
        "Artist source_specific_ids does not contain Spotify or MusicBrainz ID for TC06 (Nirvana)"
    )

    # Check some track details if tracks are present
    for track in tracks:
        assert "title" in track, f"Track missing title for TC06 (Nirvana): {track}"
        # ISRC might be missing for some global/older releases, so this check is optional or less strict
        # assert "isrc" in track, f"Track missing ISRC for TC06 (Nirvana): {track.get('title')}"
        track_source_ids = track.get("source_specific_ids")
        if track_source_ids:
            # Spotify track ID may or may not be present depending on global search results
            pass  # assert "spotify_track_id" in track_source_ids, (
            #  f"Track missing spotify_track_id for TC06 (Nirvana): {track.get('title')}"
            # )

    assert result.get("social_links", {}) is not None, "Social links field issue for TC06 (Nirvana)"
    assert result.get("genre", "") is not None, "Genre field issue for TC06 (Nirvana)"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc07_lesser_known_data(api_client: AsyncClient):
    """TC07: Test with lesser-known data where some fields might be missing.

    This test uses "Weakling - Dead as Dreams", which might not have extensive
    data in all sources (e.g., Spotify, social media). The goal is to ensure
    the API still returns a SUCCESS status with available core information
    (artist, release, tracks) even if some optional fields are null/empty.
    """
    payload = {
        "band_name": "Weakling",
        "release_name": "Dead as Dreams",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC07 (Weakling)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC07 Weakling) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC07 Weakling) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC07 (Weakling)"

    # Core fields must be present
    assert result.get("artist") is not None, "Artist field is missing for TC07 (Weakling)"
    assert "Weakling" in result["artist"].get("name", ""), "Artist name mismatch for TC07 (Weakling)"
    assert "Dead as Dreams" in result.get("release", ""), "Release name mismatch or missing for TC07 (Weakling)"

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC07 (Weakling), got {type(tracks)}"
    # For lesser-known releases, track list might be empty if no source provides it,
    # but the field itself should exist as a list.
    # However, for "Weakling - Dead as Dreams", MusicBrainz should provide tracks.
    assert len(tracks) > 0, "Tracks list should not be empty for TC07 (Weakling)"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC07 (Weakling)"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC07 (Weakling)"

    # Expect at least MusicBrainz ID for such cases, Spotify might be missing
    assert bool(artist_source_ids.get("musicbrainz_artist_id")), (
        "MusicBrainz ID for artist is expected for TC07 (Weakling)"
    )

    # Optional fields: social_links, genre. They should exist but can be empty/None.
    # The `get` method with a default handles None, and the check `is not None` ensures the key exists.
    assert result.get("social_links") is not None, "Social links field key is missing for TC07 (Weakling)"
    assert result.get("genre") is not None, "Genre field key is missing for TC07 (Weakling)"

    # For tracks, title must exist, ISRC might be missing
    for track in tracks:
        assert "title" in track and track["title"] is not None, f"Track missing title for TC07 (Weakling): {track}"
        # ISRC is often missing for underground releases
        # assert "isrc" in track, f"Track missing ISRC for TC07 (Weakling): {track.get('title')}"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc08_case_insensitivity(api_client: AsyncClient):
    """TC08: Test case-insensitivity of input parameters.

    Sends a request with mixed-case band_name, release_name, and country_code.
    The expected outcome is the same as TC01 (Metallica - Master of Puppets, US).
    """
    payload = {
        "band_name": "mEtAlLiCa",
        "release_name": "mAsTeR oF pUpPeTs",
        "country_code": "us",  # Lowercase 'us' also tests country_code case-insensitivity if applicable
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC08 (Case-Insensitive Metallica)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, (
        f"Task {task_id} (TC08 Case-Insensitive Metallica) did not complete or fetching status failed."
    )

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC08 Case-Insensitive Metallica) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing for TC08 (Case-Insensitive Metallica)"

    # Assertions similar to TC01, ensuring the data matches Metallica - Master of Puppets
    assert result.get("artist") is not None, "Artist field is missing for TC08"
    assert result["artist"].get("name") == "Metallica", "Artist name mismatch for TC08"

    expected_release_name_part = "Master of Puppets"
    actual_release_name = result.get("release", "")
    assert expected_release_name_part.lower() in actual_release_name.lower(), (
        f"Release name mismatch for TC08. Expected '{expected_release_name_part}' (case-insensitive) "
        f"to be in '{actual_release_name}'"
    )

    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC08, got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC08"

    artist_source_ids = result["artist"].get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC08"
    has_spotify_id = bool(artist_source_ids.get("spotify_artist_id"))
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_spotify_id or has_musicbrainz_id, (
        "Artist source_specific_ids does not contain Spotify or MusicBrainz ID for TC08"
    )

    # Optional: check a known track or ISRC if stability is desired for specific data points
    # This part depends on how much similarity to TC01 is strictly required by the test case definition.
    # For now, the above checks cover the core aspects of TC08.


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc09_artist_not_found(api_client: AsyncClient):
    """TC09: Test scenario where the artist is not found.

    Sends a request for a non-existent artist.
    Expected outcome is a FAILURE status with an appropriate error message.
    """
    payload = {
        "band_name": "NonExistentArtistBandName12345",
        "release_name": "Any Album Name",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC09 (Artist Not Found)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, (
        f"Task {task_id} (TC09 Artist Not Found) did not complete or fetching status failed."
    )

    assert final_response.get("status") == "FAILURE", (
        f"Task (TC09 Artist Not Found) status was not FAILURE. Response: {final_response}"
    )

    # Check for the presence of an error message in the response
    # The exact content of the error message can be flexible, but it should exist.
    error_details = final_response.get("error")
    assert error_details is not None, "Error field is missing in FAILURE response for TC09"
    assert isinstance(error_details, str), f"Error field should be a string for TC09, got {type(error_details)}"
    assert len(error_details) > 0, "Error message should not be empty for TC09"

    # Optionally, check for specific keywords in the error message if known
    # For example: "not found", "could not retrieve data", etc.
    # This makes the test more specific but also more brittle if error messages change.
    assert "no data found" in error_details.lower(), (
        f"Error message for TC09 does not seem to indicate 'no data found': {error_details}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc10_release_not_found(api_client: AsyncClient):
    """TC10: Test scenario where the release is not found for a known artist.

    Sends a request for a known artist but a non-existent release.
    Expected outcome is a FAILURE status with an appropriate error message.
    """
    payload = {
        "band_name": "Metallica",  # Known artist
        "release_name": "ThisAlbumDoesNotExistAtAll_12345",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC10 (Release Not Found)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, (
        f"Task {task_id} (TC10 Release Not Found) did not complete or fetching status failed."
    )

    assert final_response.get("status") == "FAILURE", (
        f"Task (TC10 Release Not Found) status was not FAILURE. Response: {final_response}"
    )

    error_details = final_response.get("error")
    assert error_details is not None, "Error field is missing in FAILURE response for TC10"
    assert isinstance(error_details, str), f"Error field should be a string for TC10, got {type(error_details)}"
    assert len(error_details) > 0, "Error message should not be empty for TC10"

    # Expecting a similar error message as in TC09
    assert "no data found" in error_details.lower(), (
        f"Error message for TC10 does not seem to indicate 'no data found': {error_details}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio(
    loop_scope="session",
)  # loop_scope="session" is fine as this test doesn't depend on per-function cache clearing for its core logic
async def test_tc11_missing_required_field(api_client: AsyncClient):
    """TC11: Test request with a missing required field (release_name).

    Expected behavior is an immediate HTTP 422 Unprocessable Entity response
    due to Pydantic validation, without task creation.
    """
    payload = {
        "band_name": "Metallica",
        # "release_name" is intentionally missing
    }

    # Directly make the POST request and check the immediate response
    # We don't use create_metadata_task here because we expect an immediate error, not a task ID.
    response = await api_client.post("/music/release_metadata", json=payload)

    assert response.status_code == 422, (
        f"Expected HTTP 422 for missing field, got {response.status_code}. Response: {response.text}"
    )

    response_json = response.json()
    assert "detail" in response_json, "HTTP 422 response should contain 'detail' field"

    # Pydantic errors are usually a list under response_json['detail']
    # Each item in the list is a dict describing an error.
    assert isinstance(response_json["detail"], list), "'detail' field should be a list for Pydantic errors"
    assert len(response_json["detail"]) > 0, "'detail' list should not be empty"

    # Check if one of the errors pertains to 'release_name' being missing
    found_release_name_error = False
    for error in response_json["detail"]:
        if (
            isinstance(error, dict)
            and error.get("type") == "missing"
            and error.get("loc")
            and isinstance(error["loc"], list)
            and "release_name" in error["loc"]
        ):  # Pydantic v2 "type":"missing"; Pydantic v1 "type":"value_error.missing"
            found_release_name_error = True
            break
        # For Pydantic V1, the type might be 'value_error.missing' and loc might be ['body', 'release_name']
        # For Pydantic V2, type is 'missing', loc is ['body', 'release_name'] - check 'missing' as type
        # Let's also check for a more generic Pydantic v1 style error just in case:
        if (
            isinstance(error, dict)
            and error.get("type") == "value_error.missing"
            and error.get("loc")
            and isinstance(error["loc"], list)
            and error["loc"][-1] == "release_name"
        ):
            found_release_name_error = True
            break

    assert found_release_name_error, (
        f"Did not find a Pydantic validation error for missing 'release_name'. Errors: {response_json['detail']}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")  # loop_scope="session" is fine for this Pydantic validation test
async def test_tc12_invalid_country_code(api_client: AsyncClient):
    """TC12: Test request with an invalid country_code format.

    Sends 'USA' as country_code, expecting a 2-letter format.
    Expected behavior is an immediate HTTP 422 Unprocessable Entity response.
    """
    payload = {
        "band_name": "Metallica",
        "release_name": "Master of Puppets",
        "country_code": "USA",  # Invalid format (should be 2 letters)
    }

    response = await api_client.post("/music/release_metadata", json=payload)

    assert response.status_code == 422, (
        f"Expected HTTP 422 for invalid country_code, got {response.status_code}. Response: {response.text}"
    )

    response_json = response.json()
    assert "detail" in response_json, "HTTP 422 response should contain 'detail' field for invalid country_code"

    assert isinstance(response_json["detail"], list), "'detail' field should be a list for Pydantic errors"
    assert len(response_json["detail"]) > 0, "'detail' list should not be empty for invalid country_code"

    # Check if one of the errors pertains to 'country_code'
    found_country_code_error = False
    for error in response_json["detail"]:
        # Pydantic v2 might give type 'string_too_long', 'string_too_short', or a custom regex mismatch type.
        # Pydantic v1 might give 'value_error.constr_length' or similar for min_length/max_length constraints,
        # or a pattern mismatch like 'value_error.regex'.
        # We need to check that the error location 'loc' points to 'country_code'.
        if (
            isinstance(error, dict)
            and error.get("loc")
            and isinstance(error["loc"], list)
            and "country_code" in error["loc"]
        ):
            # More specific checks for error type could be added here, e.g.:
            # error_type = error.get("type", "")
            # if "length" in error_type or "pattern" in error_type or "value_error" in error_type or "string_type" in error_type:
            # The simple location check is often robust enough.
            found_country_code_error = True
            break

    assert found_country_code_error, (
        f"Did not find a Pydantic validation error for 'country_code'. Errors: {response_json['detail']}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc13_collaboration_artist(api_client: AsyncClient):
    """TC13: Test with a collaboration release (Queen & David Bowie - Under Pressure).

    Checks how collaborations are handled, expecting one primary artist to be identified
    (e.g., Queen) and relevant metadata returned, even if it's from a compilation.
    """
    payload = {
        "band_name": "Queen & David Bowie",
        "release_name": "Under Pressure",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC13 (Collaboration)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, (
        f"Task {task_id} (TC13 Collaboration) did not complete or fetching status failed."
    )

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC13 Collaboration) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC13"

    # Check artist identification (expected to be Queen based on manual test notes)
    artist_info = result.get("artist")
    assert artist_info is not None, "Artist field is missing for TC13"
    assert artist_info.get("name") == "Queen", (
        f"Expected primary artist to be 'Queen' for TC13, got '{artist_info.get('name')}'"
    )

    # Check release name - it might be from a compilation, so use 'in'
    # The original single is just "Under Pressure". A compilation might be "Greatest Hits II (Under Pressure)".
    # Based on notes, it might be a compilation, so strict equality on release name might fail.
    # Let's ensure "Under Pressure" is part of the release name.
    actual_release_name = result.get("release", "")
    assert "Under Pressure".lower() in actual_release_name.lower(), (
        f"Release name for TC13 should include 'Under Pressure'. Got: '{actual_release_name}'"
    )

    # Check source IDs for Queen
    artist_source_ids = artist_info.get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC13"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC13"
    has_spotify_id = bool(artist_source_ids.get("spotify_artist_id"))
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_spotify_id or has_musicbrainz_id, (
        "Artist (Queen) source_specific_ids does not contain Spotify or MusicBrainz ID for TC13"
    )

    # Ensure tracks are present
    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC13, got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC13"
    # Further checks on track titles could be done if a specific compilation is always returned.
    # For now, ensuring 'Under Pressure' track exists is a good check.
    found_under_pressure_track = False
    for track in tracks:
        if "Under Pressure".lower() in track.get("title", "").lower():
            found_under_pressure_track = True
            break
    assert found_under_pressure_track, "Track 'Under Pressure' not found in the tracklist for TC13"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc14_cyrillic_input_output(api_client: AsyncClient):
    """TC14: Test with Cyrillic characters in band_name and release_name.

    Checks if the system correctly handles Unicode (Cyrillic) input and
    if the output also contains Cyrillic characters as expected.
    Data might primarily come from sources like MusicBrainz/Deezer if Spotify
    doesn't directly match Cyrillic names.
    """
    payload = {
        "band_name": "Ария",
        "release_name": "Герой асфальта",
        # country_code can be omitted or set to RU/US;
        # behavior might vary per source, but core Cyrillic handling is key.
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC14 (Cyrillic)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC14 Cyrillic) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC14 Cyrillic) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC14"

    # Check artist name
    artist_info = result.get("artist")
    assert artist_info is not None, "Artist field is missing for TC14"
    # The name might be returned exactly as "Ария" or slightly differently by some sources.
    # Using 'in' for flexibility, but exact match is preferred if consistent.
    assert "Ария" in artist_info.get("name", ""), (
        f"Expected artist name to contain 'Ария' for TC14, got '{artist_info.get('name')}'"
    )

    # Check release name
    actual_release_name = result.get("release", "")
    assert "Герой асфальта" in actual_release_name, (
        f"Release name for TC14 should contain 'Герой асфальта'. Got: '{actual_release_name}'"
    )

    # Check source IDs (expecting at least MusicBrainz or Deezer based on notes)
    artist_source_ids = artist_info.get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC14"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC14"
    # has_spotify_id = bool(artist_source_ids.get("spotify_artist_id")) # Spotify might not find it
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    has_deezer_id = bool(artist_source_ids.get("deezer_artist_id"))
    assert has_musicbrainz_id or has_deezer_id, (
        "Artist source_specific_ids for 'Ария' does not contain MusicBrainz or Deezer ID for TC14"
    )

    # Ensure tracks are present and also contain Cyrillic if applicable
    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC14, got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC14"

    # Check if at least one track title seems to be in Cyrillic (a heuristic)
    # This is a simple check; more robust would be to check for specific known Cyrillic track titles.
    # For now, we check if any track title contains a character from a Cyrillic range.
    # This is a basic check, specific track titles would be better if known and stable.
    found_cyrillic_track_title = False
    for track in tracks:
        title = track.get("title", "")
        assert title, f"Track title is empty or missing for TC14: {track}"
        # A simple heuristic: check if any char is in a common Cyrillic unicode range
        if any("\u0400" <= char <= "\u04ff" for char in title):
            found_cyrillic_track_title = True
            # We don't break here; we just want to ensure at least one seems Cyrillic
            # and all titles are asserted to exist.

    assert found_cyrillic_track_title, "No track titles appeared to contain Cyrillic characters for TC14"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="session")
async def test_tc15_live_album(api_client: AsyncClient):
    """TC15: Test with a live album (Portishead - Roseland NYC Live).

    Checks if the system correctly identifies and returns metadata for a live album.
    The key check is that the release name indicates it's a live recording.
    """
    payload = {
        "band_name": "Portishead",
        "release_name": "Roseland NYC Live",
    }
    task_id = await create_metadata_task(api_client, payload)
    assert task_id is not None, "Failed to create task for TC15 (Live Album)"

    final_response = await get_task_result(api_client, task_id)
    assert final_response is not None, f"Task {task_id} (TC15 Live Album) did not complete or fetching status failed."

    assert final_response.get("status") == "SUCCESS", (
        f"Task (TC15 Live Album) status was not SUCCESS. Response: {final_response}"
    )

    result = final_response.get("result")
    assert result is not None, "Result field is missing in successful response for TC15"

    # Check artist name
    artist_info = result.get("artist")
    assert artist_info is not None, "Artist field is missing for TC15"
    assert "Portishead" in artist_info.get("name", ""), (
        f"Expected artist name to contain 'Portishead' for TC15, got '{artist_info.get('name')}'"
    )

    # Check release name - should contain "Roseland NYC Live" and also "Live"
    actual_release_name = result.get("release", "")
    assert "Roseland NYC Live".lower() in actual_release_name.lower(), (
        f"Release name for TC15 should contain 'Roseland NYC Live'. Got: '{actual_release_name}'"
    )
    # Crucially, verify it's identified as live, as per test case notes
    assert "live" in actual_release_name.lower(), (
        f"Release name for TC15 should indicate it's a 'live' album. Got: '{actual_release_name}'"
    )

    # Check source IDs
    artist_source_ids = artist_info.get("source_specific_ids")
    assert artist_source_ids is not None, "Artist source_specific_ids are missing for TC15"
    assert isinstance(artist_source_ids, dict), "Artist source_specific_ids is not a dictionary for TC15"
    has_spotify_id = bool(artist_source_ids.get("spotify_artist_id"))
    has_musicbrainz_id = bool(artist_source_ids.get("musicbrainz_artist_id"))
    assert has_spotify_id or has_musicbrainz_id, (
        "Artist source_specific_ids for 'Portishead' does not contain Spotify or MusicBrainz ID for TC15"
    )

    # Ensure tracks are present
    tracks = result.get("tracks")
    assert isinstance(tracks, list), f"Tracks should be a list for TC15, got {type(tracks)}"
    assert len(tracks) > 0, "Tracks list should not be empty for TC15"

    # Check some track details
    for track in tracks:
        assert track.get("title"), f"Track title is empty or missing for TC15: {track}"
        # ISRC might be missing or present for live albums
        # track_source_ids = track.get("source_specific_ids")
        # if track_source_ids:
        #     assert "spotify_track_id" in track_source_ids, (
        #         f"Track missing spotify_track_id for TC15: {track.get('title')}"
        #     )

    assert result.get("social_links", {}) is not None, "Social links field issue for TC15"
    assert result.get("genre", "") is not None, "Genre field issue for TC15"
