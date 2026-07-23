import pytest
from leefomgevinglab.usecases.afval import chat


def test_select_krijgt_limit():
    out = chat.valideer_sql("SELECT * FROM afval_feit")
    assert out.lower().endswith("limit 200")


def test_bestaande_limit_te_hoog_wordt_verlaagd():
    out = chat.valideer_sql("SELECT * FROM afval_feit LIMIT 9999")
    assert "200" in out and "9999" not in out


def test_with_is_toegestaan():
    out = chat.valideer_sql("WITH x AS (SELECT 1 AS n) SELECT n FROM x")
    assert out.lower().startswith("with")


def test_trailing_semicolon_gestript():
    out = chat.valideer_sql("SELECT 1 AS n;")
    assert ";" not in out


@pytest.mark.parametrize("bad", [
    "DELETE FROM afval_feit",
    "DROP TABLE afval_feit",
    "INSERT INTO afval_feit VALUES (1)",
    "UPDATE afval_feit SET jaar=0",
    "ATTACH 'x.db'",
    "COPY afval_feit TO 'out.csv'",
    "PRAGMA database_list",
    "SELECT 1; DROP TABLE afval_feit",
    "CREATE TABLE t (x int)",
])
def test_gevaarlijke_sql_wordt_geweigerd(bad):
    with pytest.raises(chat.OngeldigeSQL):
        chat.valideer_sql(bad)
