"""Real-deck and complex-board acceptance; decisions use public session methods."""
from .adapter import AdapterError
from .acceptance_scenarios import deck, drive
from .contracts import GameSetup, MatchSeat
from .real_deck_fixtures import commander_decks


def validate_view(view):
    ids = {obj.object_id for obj in view.objects}
    if len(ids) != len(view.objects):
        raise AdapterError("DUPLICATE_OBJECT_REFERENCES")
    for obj in view.objects:
        if obj.zone == "hand" and obj.owner_id != view.viewer_id:
            raise AdapterError("OPPONENT_HAND_EXPOSED")
        if obj.hidden and (obj.characteristics is not None or obj.card_identity is not None):
            raise AdapterError("HIDDEN_IDENTITY_EXPOSED")
        if obj.copy_source_id is not None and obj.copy_source_id not in ids:
            raise AdapterError("COPY_SOURCE_NOT_VISIBLE")
    if view.decision and view.decision.player_id != view.viewer_id:
        raise AdapterError("OPPONENT_DECISION_EXPOSED")


def real_decks(adapter):
    documents = commander_decks()
    originals = [document.to_dict() for document in documents]
    report = dict(fixture_version=1, verification="deck_loading_and_extended_artifact_play",
                  mechanics_certified=False, viewers=[], turns={}, max_objects=0,
                  max_pending_options=0, selected_printing=False, artifacts_resolved={}, performance={})
    ready = set()
    printing_viewers = set()
    cast_turns = set()
    artifacts = {"Sol Ring", "Arcane Signet", "Commander's Sphere", "Mind Stone",
                 "Fellwar Stone", "Wayfarer's Bauble", "Swiftfoot Boots",
                 "Lightning Greaves", "Thought Vessel", "Mind's Eye"}

    def inspect(view):
        validate_view(view)
        if view.viewer_id not in report["viewers"]:
            report["viewers"].append(view.viewer_id)
        report["turns"][view.viewer_id] = max(view.turn or 0, report["turns"].get(view.viewer_id, 0))
        report["max_objects"] = max(report["max_objects"], len(view.objects))
        report["max_pending_options"] = max(report["max_pending_options"], len(view.decision.options) if view.decision else 0)
        report["selected_printing"] |= any(obj.card_identity and
            obj.card_identity.printing_id == "fixture-forest-M10-248" for obj in view.objects)
        if any(obj.card_identity and obj.card_identity.printing_id == "fixture-forest-M10-248"
               for obj in view.objects):
            printing_viewers.add(view.viewer_id)
        report["artifacts_resolved"][view.viewer_id] = sum(o.zone == "battlefield" and
            o.controller_id == view.viewer_id and o.characteristics and
            o.characteristics.name in artifacts for o in view.objects)
        if (view.commanders and len(view.commanders) == 2 and (view.turn or 0) >= 12
                and report["artifacts_resolved"][view.viewer_id] >= 2):
            ready.add(view.viewer_id)
        return len(ready) == 2 and len(printing_viewers) == 2

    def select(view):
        land = next((a for a in view.actions if a.kind == "play_land"), None)
        if land:
            return land
        key = (view.viewer_id, view.turn)
        lands = sum(o.zone == "battlefield" and o.controller_id == view.viewer_id and
                    o.characteristics and o.characteristics.name in {"Forest", "Island", "Mountain", "Plains"}
                    and o.tapped is False for o in view.objects)
        if lands >= 6 and key not in cast_turns:
            action = next((a for a in view.actions if a.kind == "cast_spell" and a.label in artifacts), None)
            if action:
                cast_turns.add(key)
                return action
        return None

    report.update(drive(adapter, documents, inspect, select,
        setup=GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two")), format="commander"),
        timeout=240, performance=report["performance"]))
    if [document.to_dict() for document in documents] != originals:
        raise AdapterError("SOURCE_DECK_CHANGED")
    report["termination"] = "scripted_concession_after_twelve_turns"
    report["resources"] = {"owned_jvm_memory": None, "reason": "not instrumented"}
    return report


def complex_board(adapter):
    """High-redundancy stress fixture, deliberately not a legal Commander list.

    Master of Waves creates independent Elementals and continuous bonuses; Clone
    copies it, repeats its ETB and contributes another simultaneous bonus.
    Both players build boards. No state injection or private engine access.
    """
    report = dict(verification="elemental_token_copy_board", viewers=[],
                  max_objects=0, max_stack=0, max_pending_options=0,
                  copies=False, independent_tokens=False, both_boards=False,
                  copy_printings=False,
                  multiple_bonuses=False, response_resolved=False, tokens_removed=False,
                  explicit_trigger_order=False, multi_creature_combat=False,
                  performance={})
    ready = set()
    counter_requested = False
    token_ids = {}
    attackers = set()

    def inspect(view):
        validate_view(view)
        report["max_objects"] = max(report["max_objects"], len(view.objects))
        report["max_stack"] = max(report["max_stack"], sum(o.zone == "stack" for o in view.objects))
        report["max_pending_options"] = max(report["max_pending_options"], len(view.decision.options) if view.decision else 0)
        board = [o for o in view.objects if o.zone == "battlefield" and o.characteristics]
        masters = [o for o in board if o.characteristics.name == "Master of Waves"]
        copies = [o for o in masters if o.characteristics.is_copy]
        tokens = [o for o in board if o.characteristics.name == "Elemental"]
        report["multi_creature_combat"] |= sum(len(group.attackers) for group in view.combat) >= 2
        token_ids.setdefault(view.viewer_id, set()).update(o.object_id for o in tokens)
        owners = {o.controller_id for o in masters}
        report["copies"] |= len(copies) >= 2 and len({o.object_id for o in copies}) == len(copies)
        report["copy_printings"] |= len(copies) >= 2 and all(o.card_identity and
            o.card_identity.printing_id == "selected-Clone" for o in copies)
        report["independent_tokens"] |= len(tokens) >= 6 and len({o.object_id for o in tokens}) == len(tokens)
        report["both_boards"] |= owners == {"one", "two"}
        report["multiple_bonuses"] |= any(o.characteristics.power and int(o.characteristics.power) >= 4 for o in tokens)
        if all(report[k] for k in ("copies", "copy_printings", "independent_tokens", "both_boards", "multiple_bonuses")):
            ready.add(view.viewer_id)
        graveyard = {o.characteristics.name for o in view.objects if o.zone == "graveyard" and o.characteristics}
        report["response_resolved"] |= {"Counterspell", "Evacuation"} <= graveyard and report["max_stack"] >= 2
        if len(ready) == 2 and report["response_resolved"] and not masters and not tokens:
            report["tokens_removed"] = bool(token_ids[view.viewer_id]) and not (token_ids[view.viewer_id] & {o.object_id for o in view.objects})
        return (report["tokens_removed"] and report["explicit_trigger_order"]
                and report["multi_creature_combat"] and (view.turn or 0) >= 12)

    def select(view):
        nonlocal counter_requested
        masters = [o for o in view.objects if o.zone == "battlefield" and o.controller_id == view.viewer_id
                   and o.characteristics and o.characteristics.name == "Master of Waves"]
        lands = sum(o.zone == "battlefield" and o.controller_id == view.viewer_id and o.characteristics
                    and o.characteristics.name == "Island" and o.tapped is False for o in view.objects)
        stack = [o for o in view.objects if o.zone == "stack"]
        alarm = any(o.zone == "battlefield" and o.controller_id == view.viewer_id and
                    o.characteristics and o.characteristics.name == "Intruder Alarm" for o in view.objects)
        for action in view.actions:
            if action.kind == "cast_spell" and action.label == "Counterspell" and view.viewer_id == "two" and lands >= 2 and not counter_requested and any(o.characteristics and o.characteristics.name == "Evacuation" for o in stack):
                counter_requested = True
                return action
            if stack:
                continue
            if action.kind == "play_land":
                return action
            if action.kind == "cast_spell" and action.label == "Intruder Alarm" and lands >= 3 and not alarm:
                return action
            if (len(ready) == 2 and view.viewer_id == "one" and not report["multi_creature_combat"]
                    and action.kind == "declare_attacker" and action.object_id not in attackers and len(attackers) < 2
                    and action.object_id in token_ids.get(view.viewer_id, set())):
                attackers.add(action.object_id)
                return action
            if len(ready) == 2 and report["multi_creature_combat"] and not report["tokens_removed"] and view.viewer_id == "one" and lands >= 5 and action.kind == "cast_spell" and action.label == "Evacuation":
                return action
            if alarm and lands >= 4 and action.kind == "cast_spell" and (
                (action.label == "Master of Waves" and len(masters) < 1) or
                (action.label == "Clone" and masters and len(masters) < 3)):
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family in ("target", "ability") and "triggered ability" in request.prompt.lower():
            report["explicit_trigger_order"] |= len(request.options) >= 2
            return game.choose(view.viewer_id, request.decision_id, request.options[0].option_id)
        if request.family == "boolean" and any(word in request.prompt.lower() for word in ("copy", "clone")):
            option = next(o for o in request.options if o.label == "Yes")
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        if request.family in ("target", "choice"):
            stack = {o.object_id for o in view.objects if o.zone == "stack" and o.characteristics and o.characteristics.name == "Evacuation"}
            option = next((o for o in request.options if o.object_id in stack), None)
            if option:
                return game.choose(view.viewer_id, request.decision_id, option.option_id)
            masters = {o.object_id for o in view.objects if o.zone == "battlefield" and o.characteristics
                       and o.characteristics.name == "Master of Waves"}
            option = next((o for o in request.options if o.object_id in masters), None)
            if option:
                return game.choose(view.viewer_id, request.decision_id, option.option_id)
        return None

    fixture = deck(("Island", 24), ("Master of Waves", 10), ("Clone", 10),
                   ("Intruder Alarm", 6), ("Evacuation", 5), ("Counterspell", 5))
    report.update(drive(adapter, (fixture, fixture), inspect, select, timeout=300,
                        decision_handler=respond, performance=report["performance"], allow_stack_actions=True))
    report["viewers"] = sorted(ready)
    report["termination"] = "scripted_concession_after_board_evidence"
    report["limitations"] = ["not_a_legal_commander_deck",
                             "owned_jvm_memory_unavailable"]
    return report
