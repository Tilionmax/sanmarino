import json
import unicodedata
import warnings
import fmsave

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()

def is_tracked(name, tracked):
    key = norm(name)
    if not key:
        return False
    return key in tracked or any(
        candidate in key or key in candidate
        for candidate in tracked
        if len(candidate) >= 6
    ) or "san marino calcio" in key

def appearances(row):
    return int(row.starts or 0) + int(row.substitute_appearances or 0)

def analyze_save(path, tracked_json):
    tracked_names = json.loads(tracked_json)
    tracked = {norm(name) for name in tracked_names if name}
    tracked.add(norm("San Marino Calcio"))
    messages = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        save = fmsave.open(path)
        try:
            info = save.info
            players = list(save.players())
            clubs = list(save.clubs())
            player_by_uid = {p.uid: p for p in players}
            club_by_uid = {c.uid: c for c in clubs}
            tracked_club_uids = {
                c.uid for c in clubs if is_tracked(c.name, tracked)
            }
            current_counts = {}
            current_clubs = {}
            kind_counts = {}
            maggioli_debug = {
                "uid": 2000473159,
                "currentRows": [],
                "archivedRows": []
            }
            current_stats = list(save.player_season_stats())
            for row in current_stats:
                kind = getattr(row.kind, "name", str(row.kind)).casefold().rsplit(".", 1)[-1]
                kind_counts[kind] = kind_counts.get(kind, 0) + 1
                if row.player_uid == 2000473159:
                    maggioli_debug["currentRows"].append({
                        "kind": kind, "clubUid": row.club_uid,
                        "clubName": row.club_name, "starts": row.starts,
                        "substituteAppearances": row.substitute_appearances
                    })
                if not ("league" in kind or "cup" in kind or "continental" in kind):
                    continue
                if row.club_uid not in tracked_club_uids:
                    continue
                key = (row.player_uid, row.club_uid)
                current_counts[key] = current_counts.get(key, 0) + appearances(row)
                current_clubs[key] = row.club_name

            archived_counts = {}
            archived_clubs = {}
            archived_seasons = {}
            history_count = 0
            try:
                history = list(save.player_season_history())
                history_count = len(history)
                for row in history:
                    kind = getattr(row.kind, "name", str(row.kind)).casefold().rsplit(".", 1)[-1]
                    if not ("league" in kind or "cup" in kind or "continental" in kind):
                        continue
                    if row.player_uid == 2000473159:
                        maggioli_debug["archivedRows"].append({
                            "kind": kind, "clubUid": row.club_uid,
                            "clubName": row.club_name, "starts": row.starts,
                            "substituteAppearances": row.substitute_appearances,
                            "seasonYear": int(row.season_year)
                        })
                    if row.club_uid not in tracked_club_uids:
                        continue
                    key = (row.player_uid, row.club_uid)
                    archived_counts[key] = archived_counts.get(key, 0) + appearances(row)
                    archived_clubs[key] = row.club_name
                    archived_seasons.setdefault(key, set()).add(int(row.season_year))
            except Exception as exc:
                messages.append("Historique des saisons indisponible : " + type(exc).__name__)

            rows = {}
            all_keys = set(current_counts) | set(archived_counts)
            for uid, player in player_by_uid.items():
                if player.club_uid is not None and is_tracked(player.club_name, tracked):
                    all_keys.add((uid, player.club_uid))
            for uid, club_uid in all_keys:
                player = player_by_uid.get(uid)
                club_name = (
                    current_clubs.get((uid, club_uid))
                    or archived_clubs.get((uid, club_uid))
                    or (player.club_name if player and player.club_uid == club_uid else None)
                    or (club_by_uid[club_uid].name if club_uid in club_by_uid else "Club non identifié")
                )
                if not is_tracked(club_name, tracked):
                    continue
                key = str(uid)
                if key not in rows:
                    rows[key] = {
                        "uid": uid,
                        "name": player.name if player else None,
                        "currentClub": player.club_name if player else None,
                        "currentClubUid": player.club_uid if player else None,
                        "nationId": player.nation_id if player else None,
                        "secondNationIds": list(player.second_nation_ids or ()) if player else [],
                        "clubs": [],
                        "currentSeasonAppearances": 0,
                        "archivedAppearances": 0,
                        "archivedSeasons": []
                    }
                entry = rows[key]
                if club_name and club_name not in entry["clubs"]:
                    entry["clubs"].append(club_name)
                entry["currentSeasonAppearances"] += current_counts.get((uid, club_uid), 0)
                entry["archivedAppearances"] += archived_counts.get((uid, club_uid), 0)
                entry["archivedSeasons"] = sorted(set(entry["archivedSeasons"]) | archived_seasons.get((uid, club_uid), set()))

            messages.append("Diagnostic Maggioli : " + json.dumps(maggioli_debug, ensure_ascii=False))
            messages.append("Types de statistiques saison : " + json.dumps(kind_counts, ensure_ascii=False))

            for warning in caught:
                if issubclass(warning.category, fmsave.ReaderCheckWarning):
                    messages.append(str(warning.message))

            return json.dumps({
                "game": info.game,
                "build": info.build,
                "knownBuild": info.known_build,
                "gameDate": info.game_date.isoformat() if info.game_date else None,
                "saveName": info.save_name,
                "fmsaveVersion": fmsave.__version__,
                "totalPlayersDecoded": len(players),
                "totalClubsDecoded": len(clubs),
                "currentStatsRows": len(current_stats),
                "currentStatsKinds": kind_counts,
                "historyStatsRows": history_count,
                "trackedClubUids": len(tracked_club_uids),
                "maggioliDebug": maggioli_debug,
                "players": sorted(rows.values(), key=lambda p: (p["name"] or "").casefold()),
                "warnings": messages
            }, ensure_ascii=False)
        finally:
            save.close()
