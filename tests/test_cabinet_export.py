"""La lecture pour le cabinet : ce que l'écran dit déjà, en un fichier daté, sans rien recalculer.

Le cabinet, les agents Claude Code du dossier ~/cabinet, raisonne sur le cockpit et ne doit
jamais le recalculer : deux arithmétiques du même chiffre finissent par se contredire devant
le lecteur, et c'est lui qui paie l'écart en crédibilité devant le MD. Ces tests gardent les
promesses de `manage.py cabinet` : chaque section est la sortie d'une commande qui existe,
rien n'est placé au registre, aucune lecture ne part derrière l'écran, et ce qui est tranché
arrive au cabinet avant qu'il ne le relitige.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from app import cli
from app.config import settings
from app.domain import issues as I
from app.perf import memory
from app.perf import source as source_module

SECTIONS = (
    "Où on atterrit, sommes-nous en ligne",
    "Les trois sujets de la semaine, et la surveillance",
    "Zones rouges",
    "Ce qui a changé depuis lundi dernier",
    "Engagements",
    "Ce qui est tranché",
    "La semaine",
    "Le sell-in du mois",
    "Ce qui arrive",
    "Le mois, marché par marché",
)


def _name() -> str:
    return "%s-cockpit.md" % datetime.date.today().isoformat()


def _export(folder: Path, *extra: str) -> str:
    assert cli.main(["cabinet", "--vers", str(folder)] + list(extra)) == 0
    return (folder / _name()).read_text(encoding="utf-8")


def _section(text: str, title: str) -> str:
    return text.split("\n## %s\n" % title, 1)[1].split("\n## ", 1)[0]


def test_un_dossier_de_visite_a_son_fichier_et_la_lecture_du_jour_garde_le_sien(tmp_path):
    """Deux `--marche` dans la journée ne s'écrasent pas, et le cabinet retrouve chaque
    section dans un export du jour : la lecture du jour d'un côté, un dossier par marché."""
    text = _export(tmp_path, "--marche", "Japan")
    assert "## Dossier de visite" not in text
    for title in SECTIONS:
        assert "\n## %s\n" % title in text
    dossier = tmp_path / ("%s-cockpit-japan.md" % datetime.date.today().isoformat())
    assert dossier.is_file()
    body = dossier.read_text(encoding="utf-8")
    assert "\n## Dossier de visite · Japan\n" in body
    assert "Même lecture que manage.py marche Japan." in body
    assert "## Les trois sujets" not in body
    assert body.startswith(text.split("\n## ", 1)[0])


def test_un_marche_que_le_cockpit_ne_connait_pas_est_refuse_avant_d_ecrire(tmp_path, capsys):
    """« United » pour United States donnait un dossier vide, sans MD et sans chiffre, que le
    cabinet aurait cité comme un vrai. Le nom se résout sans la casse ni les accents ; un
    inconnu arrête tout, et rien n'est écrit."""
    assert cli.main(["cabinet", "--vers", str(tmp_path), "--marche", "United"]) == 2
    assert list(tmp_path.glob("*.md")) == []
    err = capsys.readouterr().err
    assert "Marché inconnu du cockpit : United" in err
    assert "Japan" in err

    assert cli.main(["cabinet", "--vers", str(tmp_path), "--marche", "japan"]) == 0
    assert (tmp_path / ("%s-cockpit-japan.md" % datetime.date.today().isoformat())).is_file()


def test_la_lecture_est_un_fichier_date_qui_porte_chaque_section(tmp_path):
    """Les titres sont une interface : le lundi du cabinet les cherche par leur nom."""
    text = _export(tmp_path)

    for title in SECTIONS:
        assert "\n## %s\n" % title in text, title


def test_chaque_section_est_la_sortie_de_sa_commande(tmp_path, capsys):
    """La promesse qui fait le pont. Si une section disait autre chose que sa commande, le
    cabinet et le terminal liraient deux chiffres, et le lecteur ne saurait pas lequel croire."""
    printed = {}
    for title, command in (("Où on atterrit, sommes-nous en ligne", cli.cmd_track),
                           ("Les trois sujets de la semaine, et la surveillance",
                            cli.cmd_conversations),
                           ("La semaine", cli.cmd_semaine),
                           ("Le sell-in du mois", cli.cmd_sellin),
                           ("Le mois, marché par marché", cli.cmd_month)):
        command([])
        captured = capsys.readouterr()
        printed[title] = [line.rstrip() for line in (captured.out + captured.err).splitlines()
                          if line.strip()]

    text = _export(tmp_path)

    for title, lines in printed.items():
        assert lines, title
        section = _section(text, title)
        for line in lines:
            assert line in section, (title, line)


def test_la_lecture_ne_place_aucun_sujet_au_registre(tmp_path, db_session):
    """Regarder par-dessus l'épaule ne fait pas d'un sujet un sujet porté : seul l'écran
    place. Un export qui plaçait déplacerait les créneaux d'attention chaque lundi."""
    register = I.Register()
    register.observe(I.Observation(kind="gap_to_plan", scope="Japan", seen_at="2026-09-30",
                                   statement="Écart au plan qui dure"))
    memory.save(db_session, register)
    db_session.commit()
    before = [(issue.issue_id, issue.status) for issue in memory.load(db_session).issues]

    _export(tmp_path, "--marche", "Japan")

    db_session.expire_all()
    after = [(issue.issue_id, issue.status) for issue in memory.load(db_session).issues]
    assert after == before


def test_ce_qui_est_tranche_arrive_au_cabinet(tmp_path, db_session):
    """L'agent entrepôt relitigeait ce que le lecteur avait tranché, faute de lire les notes.
    Le cabinet lit les écarts acceptés, les lectures portées et les notes avant de juger."""
    register = I.Register()
    accepted = register.observe(I.Observation(kind="gap_to_plan", scope="Japan",
                                              seen_at="2026-09-30", statement="Retard du canal"))
    accepted.accept_variance(I.Arbitration(decided_by="Le lecteur", at="2026-10-01",
                                           reason="Un retard choisi, l'avance le permettait",
                                           review_on="2026-11-30"))
    read = register.observe(I.Observation(kind="gap_to_plan", scope="France",
                                          seen_at="2026-09-30", statement="Écart du retail"))
    read.reinterpret("Trois boutiques mal codées", at="2026-10-02")
    memory.save(db_session, register)
    db_session.commit()
    assert cli.main(["note", "Japan", "Livraisons baissées exprès."]) == 0

    section = _section(_export(tmp_path), "Ce qui est tranché")

    assert "accepté par Le lecteur le 2026-10-01 : Un retard choisi" in section
    assert "à revoir le 2026-11-30" in section
    assert "Trois boutiques mal codées" in section
    assert "Livraisons baissées exprès." in section
    # Le mode d'emploi du terminal n'a rien à faire dans ce que lit le cabinet.
    assert "note --forget" not in section


def test_un_reexamen_echu_se_dit(tmp_path, db_session):
    """Un écart accepté n'est pas un écart oublié : sa date passée, le cabinet le voit."""
    register = I.Register()
    issue = register.observe(I.Observation(kind="gap_to_plan", scope="Japan",
                                           seen_at="2026-01-31", statement="Retard ancien"))
    issue.accept_variance(I.Arbitration(decided_by="Le lecteur", at="2026-02-01",
                                        reason="Attendre la fin de la saison",
                                        review_on="2026-03-01"))
    memory.save(db_session, register)
    db_session.commit()

    section = _section(_export(tmp_path), "Ce qui est tranché")

    assert "Réexamens échus" in section
    assert "à revoir depuis le 2026-03-01" in section


def test_sans_dossier_la_lecture_va_dans_celui_des_reglages():
    """Le dossier par défaut reste dans le cockpit : les chiffres n'en sortent qu'exprès."""
    assert cli.main(["cabinet"]) == 0

    assert (settings.cabinet_path / _name()).is_file()
    assert "ceoos-tests-" in str(settings.cabinet_path)


def test_un_bloc_qui_tombe_se_dit_et_les_autres_restent(tmp_path, monkeypatch):
    """Une vue qui disparaît ne doit pas priver le lundi de toute sa lecture."""
    def broken(argv):
        raise RuntimeError("vue disparue")

    monkeypatch.setattr(cli, "cmd_zones", broken)

    text = _export(tmp_path)

    assert "bloc en erreur : vue disparue" in _section(text, "Zones rouges")
    assert "## La semaine" in text


def test_aucune_lecture_ne_part_derriere_l_ecran_pendant_l_export():
    """Un fil lancé par une commande du terminal meurt avec elle : la requête partait pour
    rien, et elle pouvait croiser celle du serveur ouvert dans l'autre fenêtre."""
    with source_module.disk_only():
        assert source_module.read_dataset_behind() is False
        assert source_module.read_behind("products") is False

    assert source_module._dataset_behind["running"] is False
    assert source_module._behind["products"]["running"] is False
    assert source_module._disk_only["on"] is False


def test_la_demonstration_dit_qu_aucun_chiffre_n_est_reel(tmp_path):
    text = _export(tmp_path)

    assert "Données de démonstration : aucun chiffre de ce fichier n'est réel." in text


def test_une_lecture_de_l_entrepot_rappelle_qui_a_le_droit_de_la_lire():
    """La vraie protection est le périmètre : le fichier le dit lui-même, à qui le dépose."""

    class Warehouse:
        name = "snowflake"
        label = "Snowflake"
        caveat = ""

    class Read:
        as_of = "2026-10-24"

    lines = cli._cabinet_header(Warehouse(), Read(), "2026-10-24")

    assert any("chiffres réels de la maison" in line for line in lines)
    assert not any("démonstration" in line for line in lines)


def test_une_lecture_jamais_faite_se_dit_et_une_lecture_partielle_aussi():
    assert cli._stamp_label("") == "pas encore lu"
    assert cli._stamp_label("|") == "pas encore lu"
    assert cli._stamp_label("0") == "1970-01-01 00:00 UTC"
    assert cli._stamp_label("0||60") == "1970-01-01 00:00 UTC, en partie seulement"
