import pdf
from image import Rotation


def test_distribute_cards_to_pages_splits_regular_and_oversized_cards():
    print_dict = {
        "cards": {
            "oversized-a.png": 2,
            "regular-a.png": 2,
            "regular-b.png": 1,
        },
        "backside_short_edge": {"regular-b.png": True},
        "oversized_enabled": True,
        "oversized": {"oversized-a.png": True},
    }

    pages = pdf.distribute_cards_to_pages(print_dict, columns=3, rows=2)

    assert len(pages) == 2
    assert pages[0]["oversized"] == [
        ("oversized-a.png", False),
        ("oversized-a.png", False),
    ]
    assert pages[0]["regular"] == [("regular-a.png", False), ("regular-a.png", False)]
    assert pages[1]["regular"] == [("regular-b.png", True)]


def test_distribute_cards_to_pages_fills_letter_landscape_mixed_page():
    print_dict = {
        "cards": {
            "oversized-a.png": 3,
            "regular-a.png": 2,
        },
        "oversized_enabled": True,
        "oversized": {"oversized-a.png": True},
    }

    pages = pdf.distribute_cards_to_pages(print_dict, columns=4, rows=2)

    assert pages == [
        {
            "oversized": [
                ("oversized-a.png", False),
                ("oversized-a.png", False),
                ("oversized-a.png", False),
            ],
            "regular": [
                ("regular-a.png", False),
                ("regular-a.png", False),
            ],
        }
    ]


def test_distribute_cards_to_pages_splits_unfit_four_oversized_plus_two_regular():
    print_dict = {
        "cards": {
            "oversized-a.png": 4,
            "regular-a.png": 2,
        },
        "oversized_enabled": True,
        "oversized": {"oversized-a.png": True},
    }

    pages = pdf.distribute_cards_to_pages(print_dict, columns=4, rows=2)

    assert pages == [
        {
            "oversized": [
                ("oversized-a.png", False),
                ("oversized-a.png", False),
                ("oversized-a.png", False),
                ("oversized-a.png", False),
            ],
            "regular": [],
        },
        {
            "oversized": [],
            "regular": [
                ("regular-a.png", False),
                ("regular-a.png", False),
            ],
        },
    ]


def test_distribute_cards_to_pages_allows_four_oversized_plus_two_regular_on_larger_grid():
    print_dict = {
        "cards": {
            "oversized-a.png": 4,
            "regular-a.png": 2,
        },
        "oversized_enabled": True,
        "oversized": {"oversized-a.png": True},
    }

    pages = pdf.distribute_cards_to_pages(print_dict, columns=5, rows=2)

    assert pages == [
        {
            "oversized": [
                ("oversized-a.png", False),
                ("oversized-a.png", False),
                ("oversized-a.png", False),
                ("oversized-a.png", False),
            ],
            "regular": [
                ("regular-a.png", False),
                ("regular-a.png", False),
            ],
        }
    ]


def test_make_backside_pages_preserves_mixed_front_page_buckets():
    print_dict = {
        "cards": {
            "oversized-a.png": 3,
            "regular-a.png": 2,
        },
        "backsides": {
            "oversized-a.png": "oversized-back.png",
            "regular-a.png": "regular-back.png",
        },
        "backside_default": "__back.png",
        "oversized_enabled": True,
        "oversized": {"oversized-a.png": True},
    }
    front_pages = pdf.distribute_cards_to_pages(print_dict, columns=4, rows=2)

    backside_pages = pdf.make_backside_pages(print_dict, front_pages)

    assert backside_pages == [
        {
            "oversized": [
                ("oversized-back.png", False),
                ("oversized-back.png", False),
                ("oversized-back.png", False),
            ],
            "regular": [
                ("regular-back.png", False),
                ("regular-back.png", False),
            ],
        }
    ]


def test_needs_oversized_landscape_warning_ignores_hidden_and_zero_count_cards():
    assert pdf.needs_oversized_landscape_warning(
        {
            "orient": "Portrait",
            "oversized_enabled": True,
            "cards": {"__back.png": 1, "oversized-a.png": 0},
            "oversized": {"__back.png": True, "oversized-a.png": True},
        }
    ) is False

    assert pdf.needs_oversized_landscape_warning(
        {
            "orient": "Portrait",
            "oversized_enabled": True,
            "cards": {"oversized-a.png": 1},
            "oversized": {"oversized-a.png": True},
        }
    ) is True


def test_make_backside_pages_uses_default_and_overrides():
    print_dict = {
        "backsides": {"front-a.png": "back-a.png"},
        "backside_default": "__back.png",
    }
    pages = [
        {
            "regular": [("front-a.png", False), ("front-b.png", True)],
            "oversized": [("front-c.png", False)],
        }
    ]

    backside_pages = pdf.make_backside_pages(print_dict, pages)

    assert backside_pages == [
        {
            "regular": [("back-a.png", False), ("__back.png", True)],
            "oversized": [("__back.png", False)],
        }
    ]
    assert pages[0]["regular"][0] == ("front-a.png", False)


def test_make_render_page_sequence_interleaves_backs_by_default():
    print_dict = {
        "backside_enabled": True,
        "backsides": {"front-a.png": "back-a.png", "front-b.png": "back-b.png"},
        "backside_default": "__back.png",
    }
    pages = [
        {"regular": [("front-a.png", False)], "oversized": []},
        {"regular": [("front-b.png", True)], "oversized": []},
    ]

    render_pages = pdf.make_render_page_sequence(print_dict, pages)

    assert [(page["backside"], page["front_page_number"], page["cards"]) for page in render_pages] == [
        (False, 1, {"regular": [("front-a.png", False)], "oversized": []}),
        (True, 1, {"regular": [("back-a.png", False)], "oversized": []}),
        (False, 2, {"regular": [("front-b.png", True)], "oversized": []}),
        (True, 2, {"regular": [("back-b.png", True)], "oversized": []}),
    ]


def test_make_render_page_sequence_can_put_backs_at_end():
    print_dict = {
        "backside_enabled": True,
        "backside_pages_at_end": True,
        "backsides": {"front-a.png": "back-a.png", "front-b.png": "back-b.png"},
        "backside_default": "__back.png",
    }
    pages = [
        {"regular": [("front-a.png", False)], "oversized": []},
        {"regular": [("front-b.png", True)], "oversized": []},
    ]

    render_pages = pdf.make_render_page_sequence(print_dict, pages)

    assert [(page["backside"], page["front_page_number"], page["cards"]) for page in render_pages] == [
        (False, 1, {"regular": [("front-a.png", False)], "oversized": []}),
        (False, 2, {"regular": [("front-b.png", True)], "oversized": []}),
        (True, 1, {"regular": [("back-a.png", False)], "oversized": []}),
        (True, 2, {"regular": [("back-b.png", True)], "oversized": []}),
    ]


def test_make_render_page_sequence_ignores_back_order_when_backs_disabled():
    print_dict = {
        "backside_enabled": False,
        "backside_pages_at_end": True,
        "backsides": {"front-a.png": "back-a.png"},
        "backside_default": "__back.png",
    }
    pages = [
        {"regular": [("front-a.png", False)], "oversized": []},
        {"regular": [("front-b.png", True)], "oversized": []},
    ]

    render_pages = pdf.make_render_page_sequence(print_dict, pages)

    assert [(page["backside"], page["front_page_number"], page["cards"]) for page in render_pages] == [
        (False, 1, {"regular": [("front-a.png", False)], "oversized": []}),
        (False, 2, {"regular": [("front-b.png", True)], "oversized": []}),
    ]


def test_distribute_cards_to_grid_reserves_extra_slot_for_oversized_cards():
    cards = {
        "regular": [("regular-a.png", False), ("regular-b.png", True)],
        "oversized": [("oversized-a.png", False)],
    }

    grid = pdf.distribute_cards_to_grid(cards, left_to_right=True, columns=3, rows=2)

    assert grid == [
        [
            ("oversized-a.png", False, True),
            (None, None, None),
            ("regular-a.png", False, False),
        ],
        [("regular-b.png", True, False), None, None],
    ]


def test_get_grid_coords_supports_right_to_left_layout():
    assert pdf.get_grid_coords(4, columns=3, left_to_right=True) == (1, 1)
    assert pdf.get_grid_coords(4, columns=3, left_to_right=False) == (1, 1)
    assert pdf.get_grid_coords(3, columns=3, left_to_right=False) == (1, 2)


def test_get_card_rotation_matches_backside_rules():
    assert pdf.get_card_rotation(False, False, False) is None
    assert pdf.get_card_rotation(False, True, False) == Rotation.RotateClockwise_90
    assert pdf.get_card_rotation(True, False, True) == Rotation.Rotate_180
    assert pdf.get_card_rotation(True, True, False) == Rotation.RotateCounterClockwise_90
    assert pdf.get_card_rotation(True, True, True) == Rotation.RotateClockwise_90
