from app.ui.document_view import (
    clean_display_text,
    clean_html_cell_text,
    display_region,
    document_bucket,
    document_type_label,
    is_excluded_noise_document,
    is_mock_row,
    is_potential_primary_document,
    is_primary_document,
    is_relevant_primary_document,
)


def test_document_view_classifies_parliamentary_proposals_as_primary():
    row = {
        "source": "Camera dei deputati - Dati Camera",
        "source_type": "official_api",
        "act_type": "proposta_di_legge",
    }

    assert document_bucket(row) == "proposta_legge"
    assert is_primary_document(row)


def test_document_view_includes_directly_relevant_primary_acts():
    row = {
        "source": "Camera dei deputati - Dati Camera",
        "source_type": "official_api",
        "act_type": "proposta_di_legge",
        "found_terms": {"professione_diretta": ["psicologo"]},
        "score": 9,
        "title": "Istituzione dello psicologo scolastico",
    }

    assert is_relevant_primary_document(row)


def test_document_view_excludes_primary_acts_without_thematic_signal():
    row = {
        "source": "Gazzetta Ufficiale - Serie Generale",
        "source_type": "html",
        "act_type": "decreto_legislativo",
        "found_terms": {},
        "score": 0,
        "title": "Norme di attuazione dello Statuto speciale",
    }

    assert is_primary_document(row)
    assert not is_relevant_primary_document(row)


def test_document_view_treats_trovanorme_as_normative_source():
    row = {
        "source": "Ministero della Salute - Trova Norme Salute",
        "source_type": "html",
        "act_type": "altro",
    }

    assert document_bucket(row) == "atto_normativo"
    assert is_primary_document(row)


def test_document_view_requires_combined_context_for_indirect_relevance():
    weak_row = {
        "source": "Senato della Repubblica - dati.senato.it",
        "source_type": "official_api",
        "act_type": "disegno_di_legge",
        "found_terms": {"anziani_lavoro_organizzazioni": ["lavoro"]},
        "score": 4,
        "title": "Disposizioni generiche in materia di lavoro",
    }
    combined_row = {
        "source": "Senato della Repubblica - dati.senato.it",
        "source_type": "official_api",
        "act_type": "disegno_di_legge",
        "found_terms": {
            "scuola_minori_famiglia": ["sviluppo cognitivo"],
            "tecnologia_ai_privacy": ["intelligenza artificiale"],
        },
        "score": 6,
        "title": "Dispositivi digitali, minori e sviluppo cognitivo",
    }

    assert not is_relevant_primary_document(weak_row)
    assert is_potential_primary_document(weak_row)
    assert is_relevant_primary_document(combined_row)
    assert not is_potential_primary_document(combined_row)


def test_document_view_excludes_known_noise_from_potential_acts():
    row = {
        "source": "Gazzetta Ufficiale - Serie Generale",
        "source_type": "html",
        "act_type": "decreto_legislativo",
        "found_terms": {"anziani_lavoro_organizzazioni": ["lavoro"]},
        "score": 2,
        "title": "Liquidazione coatta amministrativa di cooperativa di produzione e lavoro",
        "text": "Sostituzione del commissario liquidatore.",
    }

    assert not is_relevant_primary_document(row)
    assert not is_potential_primary_document(row)


def test_document_view_excludes_veterinary_and_wild_boar_noise_from_potential_acts():
    row = {
        "source": "Gazzetta Ufficiale - Serie Generale",
        "source_type": "html",
        "act_type": "decreto_legge",
        "found_terms": {
            "clinica_sociale": ["emergenza"],
            "sanita_welfare": ["servizi territoriali"],
        },
        "score": 4.1,
        "title": "Misure urgenti per il contenimento della peste suina africana",
        "summary": "Interventi sulla popolazione di cinghiali e attivita venatoria.",
        "text": "Misure veterinarie, biosicurezza degli allevamenti e gestione della fauna selvatica.",
    }

    assert is_primary_document(row)
    assert not is_relevant_primary_document(row)
    assert not is_potential_primary_document(row)
    assert is_excluded_noise_document(row)


def test_document_view_keeps_noise_topics_when_direct_psychological_signal_exists():
    row = {
        "source": "Gazzetta Ufficiale - Serie Generale",
        "source_type": "html",
        "act_type": "decreto_legge",
        "found_terms": {"servizi_psicologici": ["supporto psicologico"]},
        "score": 10,
        "title": "Misure per il supporto psicologico nelle emergenze sanitarie",
        "summary": "Interventi anche nei territori colpiti dalla peste suina africana.",
        "text": "Supporto psicologico agli operatori e alle comunita interessate.",
    }

    assert is_relevant_primary_document(row)
    assert not is_excluded_noise_document(row)


def test_document_view_hides_institutional_news_by_default():
    row = {
        "source": "ENPAP - Ente Nazionale Previdenza e Assistenza Psicologi",
        "source_type": "rss",
        "act_type": "altro",
    }

    assert document_bucket(row) == "informazione"
    assert not is_primary_document(row)


def test_document_view_marks_mock_rows():
    row = {
        "source": "Senato della Repubblica - mock",
        "source_type": "mock",
        "act_type": "disegno_di_legge",
    }

    assert is_mock_row(row)
    assert document_bucket(row) == "mock"


def test_document_view_combines_class_and_type_for_table():
    row = {
        "source": "Gazzetta Ufficiale - 3a Serie Speciale Regioni",
        "source_type": "html",
        "level": "regionale",
        "act_type": "legge",
    }

    assert document_type_label(row) == "Legge regionale"


def test_document_view_cleans_mojibake_for_display():
    assert clean_display_text("Gazzetta Ufficiale - 3\ufffd Serie Speciale Regioni") == (
        "Gazzetta Ufficiale - 3a Serie Speciale Regioni"
    )


def test_document_view_decodes_entities_and_typographic_quotes():
    value = (
        "L'ABBATE: &quot;Disposizioni concernenti l&rsquo;attivit&agrave; "
        "e il capo &lt;i&gt;septies&lt;/i&gt;&quot;"
    )

    assert clean_display_text(value) == (
        "L’ABBATE: “Disposizioni concernenti l’attività e il capo septies”"
    )


def test_document_view_decodes_nested_entities_for_html_cells():
    value = (
        "TENERINI: &quot;Modifiche all&amp;rsquo;articolo 26 e "
        "all&rsquo;istituzione&quot;"
    )

    assert clean_html_cell_text(value) == (
        "TENERINI: \u201cModifiche all\u2019articolo 26 e all\u2019istituzione\u201d"
    )


def test_document_view_converts_final_ascii_apostrophe_accents():
    assert clean_display_text("qualita' dell'attivita'") == "qualità dell’attività"


def test_document_view_repairs_partial_mojibake_accents():
    assert clean_display_text("attivitÃ di qualitÃ") == "attività di qualità"
    assert clean_display_text("Gulino Ãˆ prevenzione") == "Gulino È prevenzione"
    assert clean_display_text("cos’Ã¨") == "cos’è"
    assert clean_display_text("COSÃŒ COME SEI") == "COSÌ COME SEI"
    assert clean_display_text("Questo è ciÃ² che conta") == "Questo è ciò che conta"
    assert clean_display_text("AscoltaMI: Â Servizio") == "AscoltaMI: Servizio"


def test_document_view_infers_region_for_regional_rows():
    row = {
        "source": "Gazzetta Ufficiale - 3a Serie Speciale Regioni",
        "source_type": "html",
        "level": "regionale",
        "region": "",
        "title": "LEGGE REGIONALE LAZIO 1 giugno 2026",
        "summary": "Disposizioni sui servizi territoriali.",
        "text": "",
    }

    assert display_region(row) == "Lazio"
