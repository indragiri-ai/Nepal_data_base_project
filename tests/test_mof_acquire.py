"""Offline tests for the MoF publications harvester's pure parsing logic
(no network, no DB). Fixture HTML fragments are trimmed, real excerpts taken
from live mof.gov.np category listings (2026-09-03 recon) — one table-layout
row (bulletin) and one card-grid entry (economic-survey), both real shapes
this CMS serves.
"""

from __future__ import annotations

from ingestion.mof.acquire import (
    discover_pagination_max,
    extract_primary_section,
    parse_bs_date_guess,
    parse_grid_cards,
    parse_listing,
    parse_table_rows,
)

TABLE_HTML = """
<table class="table">
<tbody>
<tr>
    <td>1</td>
    <td>अर्थ बुलेटिन, जेठ अंक (२०८३)</td>
    <td>साउन ८, २०८३, शुक्रबार १६:०</td>
    <td>
        <a href="https://giwmscdnone.gov.np/media/pdf_upload/Jestha%20Bulletin.pdf" target="_blank">
            <i class="fas fa-file-pdf"></i>
        </a>
    </td>
    <td>
        <a href="
                /content/1774/earth-bulletin--may-issue--2083-/
            " class="info__link" data-title="अर्थ बुलेटिन, जेठ अंक (२०८३)" data-pdf="">
            <span><i class="fas fa-eye"></i></span>
        </a>
    </td>
</tr>
<tr>
    <td>2</td>
    <td>अर्थ बुलेटिन, बैशाख अंक (२०८३)</td>
    <td>असार ३, २०८३, बुधबार १२:१४</td>
    <td>
        <a href="https://giwmscdnone.gov.np/media/pdf_upload/Baisakh.pdf" target="_blank">
            <i class="fas fa-file-pdf"></i>
        </a>
    </td>
    <td>
        <a href="
                /content/1753/earth-bulletin--baisakh-issue--2083-/
            " class="info__link" data-title="अर्थ बुलेटिन, बैशाख अंक (२०८३)" data-pdf="">
            <span><i class="fas fa-eye"></i></span>
        </a>
    </td>
</tr>
</tbody>
</table>
<div class="pagination">
    <a href="?page=1" class="pagination__btn active">1</a>
    <a href="?page=2" class="pagination__btn">2</a>
    <a href="?page=3" class="pagination__btn">3</a>
</div>
"""

GRID_HTML = """
<div class="category-1-grid">
    <div class="grid__card">
        <div class="card__img">
            <a href="
                        /content/1803/economic-survey/
                    ">
                <img src="https://giwmscdnone.gov.np/static/assets/image/newlogo.png" alt="">
            </a>
        </div>
        <div class="card__details">
            <h3 class="card__title">
                <a href="
                        /content/1803/economic-survey/
                    ">
                    आर्थिक सर्वेक्षण 2025/26
                </a>
            </h3>
            <div class="post__meta">
                <div class="meta post__date">
                    <p>
                        <i class="fas fa-clock"></i>
                        १६ भदौ, २०८३
                    </p>
                </div>
            </div>
        </div>
    </div>
</div>
"""

NO_PAGINATION_HTML = "<html><body>no pagination links here</body></html>"

# Real bug found 2026-09-03: a category page can carry a SECOND section,
# "सम्बन्धित" (Related), using the identical grid__card markup but drawn
# from across the whole site — not this category. Reproduces the shape from
# a live half-yearly-elemental-assessment page 2 fetch.
GRID_WITH_RELATED_SECTION_HTML = """
<div class="title-6 translate-title">
    <h2 class="category__title">
        <a href=" javascript:void(0); ">अर्धवार्षिक मूल्याङ्कन</a>
    </h2>
</div>
<div class="category-1-grid">
    <div class="grid__card">
        <div class="card__details">
            <h3 class="card__title">
                <a href="
                        /content/155/press-note--semi-yearly/
                    ">
                    प्रेस नोट - अर्धवार्षिक
                </a>
            </h3>
            <div class="post__meta">
                <div class="meta post__date">
                    <p><i class="fas fa-clock"></i> १० माघ, २०७७</p>
                </div>
            </div>
        </div>
    </div>
</div>
<div class="title-6 translate-title">
    <h2 class="category__title">
        <a href=" javascript:void(0); ">सम्बन्धित</a>
    </h2>
</div>
<div class="detail__block">
    <div class="detail__block-grid">
        <div class="grid__card">
            <div class="card__details">
                <h3 class="card__title">
                    <a href="
                            /content/1808/press-release--unrelated-adb-grant/
                        ">
                        प्रेस विज्ञप्ति: unrelated ADB grant news
                    </a>
                </h3>
                <div class="post__meta">
                    <div class="meta post__date">
                        <p><i class="fas fa-clock"></i> १ भदौ, २०८३</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""


def test_table_rows_extract_direct_pdf_and_content_id() -> None:
    rows = parse_table_rows(TABLE_HTML, "bulletin")
    assert len(rows) == 2
    first = rows[0]
    assert first.content_id == "1774"
    assert first.slug == "earth-bulletin--may-issue--2083-"
    assert first.title_ne == "अर्थ बुलेटिन, जेठ अंक (२०८३)"
    assert first.pdf_url == "https://giwmscdnone.gov.np/media/pdf_upload/Jestha%20Bulletin.pdf"
    assert first.bs_date_guess == "2083-04-08"


def test_grid_cards_have_no_direct_pdf_url() -> None:
    cards = parse_grid_cards(GRID_HTML, "economic-survey")
    assert len(cards) == 1
    card = cards[0]
    assert card.content_id == "1803"
    assert card.slug == "economic-survey"
    assert card.title_ne == "आर्थिक सर्वेक्षण 2025/26"
    assert card.pdf_url is None
    assert card.bs_date_guess == "2083-05-16"


def test_parse_listing_prefers_table_then_falls_back_to_grid() -> None:
    assert len(parse_listing(TABLE_HTML, "bulletin")) == 2
    assert len(parse_listing(GRID_HTML, "economic-survey")) == 1
    assert parse_listing(NO_PAGINATION_HTML, "bulletin") == []


def test_discover_pagination_max() -> None:
    assert discover_pagination_max(TABLE_HTML) == 3
    assert discover_pagination_max(NO_PAGINATION_HTML) == 1


def test_bs_date_guess_handles_both_layouts() -> None:
    # month-first (table layout), with a trailing weekday + time
    assert parse_bs_date_guess("साउन ८, २०८३, शुक्रबार १६:०") == "2083-04-08"
    # day-first (card-grid layout), no trailing weekday
    assert parse_bs_date_guess("१६ भदौ, २०८३") == "2083-05-16"
    assert parse_bs_date_guess("पुष २७, २०८१, शनिबार २१:२५") == "2081-09-27"


def test_bs_date_guess_never_guesses_unrecognised_text() -> None:
    assert parse_bs_date_guess("garbage text with no date") is None
    assert parse_bs_date_guess("") is None
    assert parse_bs_date_guess("अज्ञातमहिना १, २०८३") is None  # unknown month name


def test_related_section_noise_is_excluded() -> None:
    """A second 'सम्बन्धित' (Related) section shares grid__card markup with
    the real listing but is drawn from the whole site — it must not leak in."""
    pubs = parse_listing(GRID_WITH_RELATED_SECTION_HTML, "half-yearly-elemental-assessment")
    ids = {p.content_id for p in pubs}
    assert ids == {"155"}
    assert "1808" not in ids


def test_extract_primary_section_stops_at_second_heading() -> None:
    section = extract_primary_section(GRID_WITH_RELATED_SECTION_HTML)
    assert "content/155" in section
    assert "content/1808" not in section
