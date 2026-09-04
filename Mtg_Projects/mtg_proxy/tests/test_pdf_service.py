from services import pdf_service


def test_generate_pdf_splits_backs_into_second_file(monkeypatch, tmp_path):
    calls = []

    def fake_generate(state, size, path, print_fn, *, page_side="both"):
        result = object()
        calls.append((path, page_side, result))
        return result

    monkeypatch.setattr(pdf_service.pdf, "generate", fake_generate)
    front_path = str(tmp_path / "deck.pdf")

    result = pdf_service.generate_pdf(
        {
            "backside_enabled": True,
            "backside_separate_file": True,
        },
        (612, 792),
        front_path,
        lambda _message: None,
    )

    assert [(path, side) for path, side, _pages in calls] == [
        (front_path, "front"),
        (str(tmp_path / "deck_backs.pdf"), "back"),
    ]
    assert result.pages is calls[0][2]
    assert result.backside_pages is calls[1][2]
    assert result.backside_pdf_path == str(tmp_path / "deck_backs.pdf")


def test_generate_pdf_keeps_combined_output_by_default(monkeypatch, tmp_path):
    calls = []

    def fake_generate(state, size, path, print_fn, *, page_side="both"):
        calls.append((path, page_side))
        return object()

    monkeypatch.setattr(pdf_service.pdf, "generate", fake_generate)
    front_path = str(tmp_path / "deck.pdf")

    result = pdf_service.generate_pdf(
        {"backside_enabled": True},
        (612, 792),
        front_path,
        lambda _message: None,
    )

    assert calls == [(front_path, "both")]
    assert result.backside_pages is None
    assert result.backside_pdf_path is None
