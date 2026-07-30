"""Generate deterministic per-match telemetry reports from captured JSONL."""

import json
from collections import Counter
from pathlib import Path


def _read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _rabbit(frame, bot_id):
    data = frame.get("data") if isinstance(frame, dict) else None
    rabbits = data.get("rabbits") if isinstance(data, dict) else None
    if not isinstance(rabbits, list):
        return None
    expected = str(bot_id)
    return next((item for item in rabbits if str(item.get("id")).removeprefix("ai:") == expected), None)


def _settlement_row(settlement, bot_id):
    result = settlement.get("result") if isinstance(settlement, dict) else None
    rankings = result.get("ranking") if isinstance(result, dict) else None
    if not isinstance(rankings, list):
        return {}
    expected = str(bot_id)
    return next((row for row in rankings if str(row.get("botId")) == expected), {})


def build_match_report(directory):
    directory = Path(directory)
    metadata = _read_json(directory / "metadata.json")
    settlement = _read_json(directory / "settlement.json")
    frames = _read_jsonl(directory / "frames.jsonl")
    commands = _read_jsonl(directory / "commands.jsonl")
    bot_id = metadata.get("botId")

    mode_counts = Counter()
    reason_counts = Counter()
    command_counts = Counter()
    attack_values = []
    target_counts = Counter()
    turn_switches = 0
    previous_turn = None
    max_idle = 0.0
    for row in commands:
        command = row.get("command") or {}
        decision = row.get("decision") or {}
        command_type = command.get("commandType")
        command_counts[command_type] += 1
        if command_type == "setAttackValue":
            try:
                attack_values.append(float(command.get("data")))
            except (TypeError, ValueError):
                pass
        if command_type in ("turnLeft", "turnRight"):
            if previous_turn is not None and command_type != previous_turn:
                turn_switches += 1
            previous_turn = command_type
        mode_counts[decision.get("mode") or "UNKNOWN"] += 1
        reason_counts[decision.get("reason") or "unknown"] += 1
        if decision.get("targetId") is not None:
            target_counts[str(decision["targetId"])] += 1
        max_idle = max(max_idle, float(decision.get("idleSeconds") or 0))

    contacts = 0
    idle_penalties = 0
    obstacle_like_losses = 0
    heart_pickups = 0
    energy_waste = []
    previous = None
    previous_elapsed = None
    for frame in frames:
        if frame.get("commandType") != "refreshData":
            continue
        me = _rabbit(frame, bot_id)
        if me is None:
            continue
        elapsed = float((frame.get("data") or {}).get("elapsedSeconds") or 0)
        if previous is not None:
            energy_drop = float(previous.get("energy") or 0) - float(me.get("energy") or 0)
            score_drop = float(previous.get("score") or 0) - float(me.get("score") or 0)
            rebound_started = bool(me.get("rebounding")) and not bool(previous.get("rebounding"))
            if energy_drop > 0 or abs(score_drop) == 1 or rebound_started:
                contacts += 1
            if score_drop >= 3:
                idle_penalties += 1
            elif score_drop == 1 and energy_drop <= 0:
                obstacle_like_losses += 1
            if bool(me.get("invincible") or me.get("attacking")) and not bool(
                    previous.get("invincible") or previous.get("attacking")):
                heart_pickups += 1
            if previous_elapsed is not None and int(previous_elapsed // 30) != int(elapsed // 30):
                energy_waste.append(float(previous.get("energy") or 0))
        previous = me
        previous_elapsed = elapsed

    final = _settlement_row(settlement, bot_id)
    return {
        "schemaVersion": 1,
        "match": {
            "matchCode": metadata.get("matchCode"),
            "matchId": metadata.get("matchId"),
            "matchType": metadata.get("matchType"),
            "roundNo": metadata.get("roundNo"),
            "gameNo": metadata.get("gameNo"),
            "gamesPerTable": metadata.get("gamesPerTable"),
            "strategyHash": metadata.get("strategyHash"),
        },
        "result": {
            "rank": final.get("rank", settlement.get("resultRank")),
            "score": final.get("score"),
            "points": final.get("points"),
            "deathCount": final.get("deathCount"),
            "forestHeartCount": final.get("forestHeartCount"),
        },
        "decisions": {
            "count": len(commands),
            "modes": dict(mode_counts),
            "reasons": dict(reason_counts),
            "commands": dict(command_counts),
            "targets": dict(target_counts),
            "turnDirectionSwitches": turn_switches,
            "maxEstimatedIdleSeconds": round(max_idle, 3),
        },
        "energy": {
            "attackSetCount": len(attack_values),
            "averageAttackSet": (
                round(sum(attack_values) / len(attack_values), 3) if attack_values else None),
            "maxAttackSet": max(attack_values) if attack_values else None,
            "energyBeforeResets": energy_waste,
        },
        "events": {
            "estimatedContacts": contacts,
            "estimatedIdlePenalties": idle_penalties,
            "estimatedObstacleLosses": obstacle_like_losses,
            "estimatedHeartPickups": heart_pickups,
        },
    }


def _markdown(report):
    result = report["result"]
    decisions = report["decisions"]
    energy = report["energy"]
    events = report["events"]
    return "\n".join([
        f"# Match report: {report['match'].get('matchCode')}",
        "",
        f"- Rank: {result.get('rank')}",
        f"- Score: {result.get('score')}",
        f"- Points: {result.get('points')}",
        f"- Decisions: {decisions.get('count')}",
        f"- Mode counts: `{json.dumps(decisions.get('modes'), ensure_ascii=False)}`",
        f"- Estimated contacts: {events.get('estimatedContacts')}",
        f"- Estimated idle penalties: {events.get('estimatedIdlePenalties')}",
        f"- Estimated obstacle losses: {events.get('estimatedObstacleLosses')}",
        f"- Attack presets: {energy.get('attackSetCount')}",
        f"- Average attack preset: {energy.get('averageAttackSet')}",
        "",
    ])


def generate_match_report(directory):
    directory = Path(directory)
    report = build_match_report(directory)
    json_path = directory / "match-report.json"
    markdown_path = directory / "match-report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path
