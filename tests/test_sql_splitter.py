from ingomob.warehouse import split_sql


def test_semicolon_inside_string_literal_is_not_a_separator():
    stmts = split_sql("SELECT ';' AS a; SELECT 2;")
    assert len(stmts) == 2
    assert "';'" in stmts[0]


def test_double_dash_inside_literal_survives():
    """Regression: the previous implementation truncated this to SELECT 'a."""
    stmts = split_sql("SELECT 'a--b' AS x;")
    assert stmts == ["SELECT 'a--b' AS x"]


def test_line_and_block_comments_removed():
    stmts = split_sql("-- header\n/* block */\nSELECT 1; -- trailing\nSELECT 2;")
    assert len(stmts) == 2


def test_quoted_identifier_with_dashes():
    stmts = split_sql('SELECT "we--ird" FROM t;')
    assert 'we--ird' in stmts[0]


def test_empty_script():
    assert split_sql("   \n-- nothing\n") == []
