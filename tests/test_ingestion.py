import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpa.ingestion import sec_client
from fpa.ingestion.bronze import LOG_NAME, archive, latest_snapshot
from fpa.ingestion.collect import run
from fpa.ingestion.inventory import concepts_inventory, filings_table
from fpa.ingestion.sec_client import SecClient, normalize_cik

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --- CIK -------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["27419", 27419, "0000027419", "CIK0000027419", " 27419 "])
def test_normalize_cik_pads_to_ten_digits(raw):
    assert normalize_cik(raw) == "0000027419"


@pytest.mark.parametrize("raw", ["", "abc", "0", "12345678901"])
def test_normalize_cik_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_cik(raw)


# --- Client ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status, content=b"{}"):
        self.status_code = status
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        return self.responses.pop(0)


def test_client_requires_contact_in_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(ValueError):
        SecClient(user_agent="no contact")


def test_client_sets_user_agent_and_retries_on_429(monkeypatch):
    monkeypatch.setattr(sec_client.time, "sleep", lambda s: None)
    session = FakeSession([FakeResponse(429), FakeResponse(503), FakeResponse(200, b'{"ok": 1}')])
    client = SecClient(user_agent="Test test@example.org", session=session)
    resp = client.company_facts(27419)
    assert resp.content == b'{"ok": 1}'
    assert session.headers["User-Agent"] == "Test test@example.org"
    assert session.urls == [sec_client.COMPANY_FACTS_URL.format(cik="0000027419")] * 3


def test_client_raises_after_retries(monkeypatch):
    monkeypatch.setattr(sec_client.time, "sleep", lambda s: None)
    session = FakeSession([FakeResponse(503)] * 3)
    client = SecClient(user_agent="Test test@example.org", session=session, max_retries=2)
    with pytest.raises(RuntimeError):
        client.submissions(27419)


# --- Bronze ------------------------------------------------------------------


def test_archive_writes_raw_bytes_and_logs(tmp_path):
    content = load("companyfacts_sample.json")
    rec = archive(
        content,
        root=tmp_path,
        source="sec",
        dataset="companyfacts",
        cik="0000027419",
        url="https://x",
        retrieved_at=NOW,
    )
    target = tmp_path / rec.path
    assert rec.path == "sec/companyfacts/CIK0000027419/2026-11-13/companyfacts.json"
    assert target.read_bytes() == content
    assert rec.status == "new"
    log = [json.loads(line) for line in (tmp_path / LOG_NAME).read_text().splitlines()]
    assert log[0]["sha256"] == rec.sha256 and log[0]["bytes"] == len(content)


def test_archive_same_content_is_unchanged(tmp_path):
    content = load("companyfacts_sample.json")
    kwargs = dict(
        root=tmp_path, source="sec", dataset="companyfacts", cik="0000027419", url="https://x", retrieved_at=NOW
    )
    archive(content, **kwargs)
    second = archive(content, **kwargs)
    assert second.status == "unchanged"
    assert len((tmp_path / LOG_NAME).read_text().splitlines()) == 2


def test_archive_rejects_non_json(tmp_path):
    with pytest.raises(ValueError):
        archive(
            b"<html>error</html>",
            root=tmp_path,
            source="sec",
            dataset="companyfacts",
            cik="0000027419",
            url="https://x",
            retrieved_at=NOW,
        )


def test_latest_snapshot_picks_most_recent_date(tmp_path):
    content = load("companyfacts_sample.json")
    for day in (1, 12):
        archive(
            content,
            root=tmp_path,
            source="sec",
            dataset="companyfacts",
            cik="0000027419",
            url="https://x",
            retrieved_at=NOW.replace(day=day),
        )
    assert latest_snapshot(tmp_path, "sec", "companyfacts", "0000027419").parent.name == "2026-11-12"


# --- Inventaires -----------------------------------------------------------------


def test_concepts_inventory_detects_revenue_tag_change():
    inv = concepts_inventory(json.loads(load("companyfacts_sample.json")))
    rev = inv.set_index("concept")
    assert rev.loc["Revenues", "last_end"] == "2015-01-31"
    assert rev.loc["RevenueFromContractWithCustomerExcludingAssessedTax", "first_end"] == "2018-02-03"
    assert rev.loc["Revenues", "forms"] == "10-K,10-Q"


def test_filings_table_keeps_financial_forms_and_builds_urls():
    df = filings_table(json.loads(load("submissions_sample.json")))
    assert set(df["form"]) == {"10-K", "10-Q", "8-K"}
    assert df.loc[0, "filing_date"] == "2026-08-20"
    assert df.loc[0, "url"] == ("https://www.sec.gov/Archives/edgar/data/27419/000002741926000050/tgt-20260801.htm")


# --- Collecte complète (sans réseau) ----------------------------------------------


class FixtureClient:
    def company_facts(self, cik):
        return sec_client.SecResponse("https://facts", 200, load("companyfacts_sample.json"))

    def submissions(self, cik):
        return sec_client.SecResponse("https://subs", 200, load("submissions_sample.json"))


def test_run_archives_both_datasets_and_inventories(tmp_path):
    summary = run("27419", tmp_path, FixtureClient(), now=NOW)
    assert summary["entity"] == "TARGET CORP (fixture)"
    day = tmp_path / "sec" / "companyfacts" / "CIK0000027419" / "2026-11-13"
    assert (day / "concepts_inventory.csv").exists()
    assert (tmp_path / "sec/submissions/CIK0000027419/2026-11-13/filings.csv").exists()
    assert summary["filings"] == 3


# --- Communiqués de résultats -------------------------------------------------------


def test_outlook_paragraphs_keeps_guidance_and_bullets():
    from fpa.ingestion.earnings_releases import outlook_paragraphs

    html = (
        "<p>Revenue was strong this quarter and the team executed well overall.</p>"
        "<p>The Company has the following expectations for full-year 2025:</p>"
        "<p>•Net Sales growth in a range around 1 percent, reflecting comparable sales around flat</p>"
        "<p>•An effective tax rate of 23 to 24 percent for the full year as a whole</p>"
        "<p>Statements in this release regarding guidance are forward-looking statements within the Act.</p>"
        "<p>For the fourth quarter, the Company expects comparable sales in a wide range around flat.</p>"
    )
    paras = outlook_paragraphs(html)
    assert len(paras) == 4
    assert not any("forward-looking" in p for p in paras)


def test_pick_exhibit_99_and_earnings_filter():
    import pandas as pd

    from fpa.ingestion.earnings_releases import earnings_filings, pick_exhibit_99

    index = {"directory": {"item": [{"name": "tgt-20220518.htm"}, {"name": "a2022q1ex-99.htm"}]}}
    assert pick_exhibit_99(index) == "a2022q1ex-99.htm"
    assert pick_exhibit_99({"directory": {"item": [{"name": "x.htm"}]}}) is None
    filings = pd.DataFrame(
        {
            "form": ["8-K", "8-K", "10-Q"],
            "items": ["2.02,9.01", "5.07", ""],
            "filing_date": ["2026-08-19", "2026-06-11", "2026-08-20"],
        }
    )
    assert earnings_filings(filings)["filing_date"].tolist() == ["2026-08-19"]
