"""Une base qui porte déjà des lignes, et des modèles qui ont bougé.

Le défaut est arrivé en vrai : une colonne ajoutée à `management_issues` a rendu illisible
une base qui portait de vrais sujets. `create_all` ne crée que des tables manquantes, et
la commande s'arrêtait sur « no such column ». La réponse courte — effacer la base — aurait
effacé la mémoire, c'est-à-dire la seule chose que ce module existe pour garder.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, MetaData, String, Table, text

from app import db


def _probe(*extra) -> "MetaData":
    schema = MetaData()
    Table("schema_probe", schema, Column("id", String(8), primary_key=True), *extra)
    return schema


def test_a_column_added_to_a_model_reaches_a_base_that_already_has_rows():
    before = _probe()
    before.create_all(bind=db.engine)
    with db.engine.begin() as connection:
        connection.execute(text("INSERT INTO schema_probe (id) VALUES ('keep-me')"))
    after = _probe(Column("flag", Boolean, nullable=False, default=False))

    try:
        added, refused = db.add_missing_columns(after)

        assert added == ["schema_probe.flag"]
        assert refused == []
        with db.engine.begin() as connection:
            row = connection.execute(
                text("SELECT id, flag FROM schema_probe")).fetchone()
        # La ligne d'avant survit et prend la valeur de départ du modèle, jamais NULL :
        # une colonne obligatoire laissée à NULL rendrait la table illisible autrement.
        assert row[0] == "keep-me" and not row[1]
    finally:
        after.drop_all(bind=db.engine)


def test_running_twice_adds_nothing_the_second_time():
    schema = _probe(Column("label", String(20), nullable=False, default=""))
    _probe().create_all(bind=db.engine)
    try:
        db.add_missing_columns(schema)

        assert db.add_missing_columns(schema) == ([], [])
        assert db.pending_columns(schema) == []
    finally:
        schema.drop_all(bind=db.engine)


def test_a_column_whose_value_de_depart_se_calcule_is_named_and_not_invented():
    """Un identifiant ou un horodatage n'a pas de littéral SQL. Le remplir d'une valeur
    choisie par la migration donnerait à chaque ligne existante la même identité — un
    dégât silencieux, exactement la classe de défaut que ce projet traque. La colonne est
    donc nommée et laissée à l'appelant."""
    schema = _probe(Column("token", String(8), nullable=False, default=lambda: "x"))
    _probe().create_all(bind=db.engine)
    try:
        added, refused = db.add_missing_columns(schema)

        assert added == []
        assert refused and refused[0].startswith("schema_probe.token")
    finally:
        schema.drop_all(bind=db.engine)


def test_a_table_that_does_not_exist_yet_is_not_a_missing_column():
    """Elle est créée entière par `create_all`. L'annoncer colonne par colonne ferait
    passer une création ordinaire pour une migration."""
    schema = _probe(Column("flag", Boolean, nullable=False, default=False))
    schema.drop_all(bind=db.engine)

    assert db.pending_columns(schema) == []
