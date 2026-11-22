import json
import unicodedata
import warnings
import fmsave

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()

CLUB_ALIASES = {
    "ac libertas": "AC Libertas", "libertas": "AC Libertas",
    "fc domagnano": "FC Domagnano", "domagnano": "FC Domagnano",
    "fc fiorentino": "FC Fiorentino", "fiorentino": "FC Fiorentino",
    "ss folgore/falciano": "SS Folgore/Falciano", "folgore/falciano": "SS Folgore/Falciano", "folgore": "SS Folgore/Falciano",
    "ac juvenes-dogana": "AC Juvenes-Dogana", "juvenes/dogana": "AC Juvenes-Dogana", "juvenes-dogana": "AC Juvenes-Dogana", "juvenes dogana": "AC Juvenes-Dogana",
    "la fiorita 1967": "La Fiorita 1967", "la fiorita": "La Fiorita 1967",
    "ss pennarossa": "SS Pennarossa", "pennarossa calcio": "SS Pennarossa", "pennarossa": "SS Pennarossa",
    "ss san giovanni": "SS San Giovanni", "san giovanni": "SS San Giovanni",
    "san marino academy": "San Marino Academy",
    "sc faetano": "SC Faetano", "faetano": "SC Faetano",
    "sp cailungo": "SP Cailungo", "cailungo": "SP Cailungo",
    "ss cosmos": "SS Cosmos", "cosmos": "SS Cosmos",
    "ss murata": "SS Murata", "murata": "SS Murata",
    "tre fiori fc": "Tre Fiori FC", "tre fiori": "Tre Fiori FC",
    "sp tre penne": "SP Tre Penne", "tre penne": "SP Tre Penne",
    "ac virtus acquaviva": "AC Virtus Acquaviva", "ss virtus": "AC Virtus Acquaviva", "virtus": "AC Virtus Acquaviva",
    "san marino calcio": "San Marino Calcio"
}

def canonical_club(name):
    return CLUB_ALIASES.get(norm(name))

def is_tracked(name, tracked):
    canonical = canonical_club(name)
    # Correspondance par alias exact uniquement : un club étranger tel que
    # Tromsø ne peut pas être retenu par simple ressemblance de nom.
    return canonical is not None and norm(canonical) in tracked

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
            tracked_clubs_found = sorted({
                canonical_club(c.name) for c in clubs
                if canonical_club(c.name) is not None
                and norm(canonical_club(c.name)) in tracked
            }, key=lambda value: norm(value))
            tracked_club_names = sorted(
                {str(name).strip() for name in tracked_names if name},
                key=norm
            )
            tracked_clubs_missing = [
                name for name in tracked_club_names
                if norm(name) not in {norm(found) for found in tracked_clubs_found}
            ]
            current_counts = {}
            current_clubs = {}
            kind_counts = {}
            target_game_id = 2000214775
            galesi_candidates = [
                p for p in players
                if "galesi" in norm(p.name)
                or p.uid == target_game_id
                or p.unique_id == target_game_id
            ]
            candidate_uids = {p.uid for p in galesi_candidates}
            galesi_debug = {
                "targetGameId": target_game_id,
                "playersNamedGalesi": [{
                    "uid": p.uid, "uniqueId": p.unique_id, "name": p.name,
                    "clubUid": p.club_uid, "clubName": p.club_name,
                    "nationId": p.nation_id,
                    "secondNationIds": list(p.second_nation_ids or ())
                } for p in galesi_candidates],
                "statsByCandidateUid": {},
                "archivedRowsByCandidateUid": {},
                "matchRowsByCandidateUid": {},
                "currentRowsByUid": [],
                "currentRowsByUniqueId": [],
                "currentRowsByName": [],
                "archivedRowsByUid": [],
                "archivedRowsByUniqueId": [],
                "archivedRowsByName": [],
                "matchRowsByUid": [],
                "matchRowsByUniqueId": [],
                "matchRowsByName": [],
                "statsUidDiagnostics": {}
            }
            current_stats = list(save.player_season_stats())
            player_uids = {p.uid for p in players}
            nonnull_stat_uids = {row.player_uid for row in current_stats if row.player_uid is not None}
            galesi_debug["statsUidDiagnostics"] = {
                "rowsWithPlayerUid": sum(1 for row in current_stats if row.player_uid is not None),
                "distinctStatsPlayerUids": len(nonnull_stat_uids),
                "statsUidsMatchingDecodedPlayers": len(nonnull_stat_uids & player_uids),
                "sampleRows": [{ "playerUid": row.player_uid, "playerName": row.player_name, "kind": getattr(row.kind, "name", str(row.kind)) } for row in current_stats[:5]]
            }
            for row in current_stats:
                kind = getattr(row.kind, "name", str(row.kind)).casefold().rsplit(".", 1)[-1]
                kind_counts[kind] = kind_counts.get(kind, 0) + 1
                row_info = {
                    "playerUid": row.player_uid, "playerName": row.player_name,
                    "kind": kind, "clubUid": row.club_uid,
                    "clubName": row.club_name, "starts": row.starts,
                    "substituteAppearances": row.substitute_appearances
                }
                if row.player_uid in candidate_uids:
                    galesi_debug["statsByCandidateUid"].setdefault(str(row.player_uid), []).append(row_info)
                if row.player_uid == -1:
                    galesi_debug["currentRowsByUid"].append(row_info)
                if row.player_uid == -2:
                    galesi_debug["currentRowsByUniqueId"].append(row_info)
                if norm(row.player_name) == norm("Vincenzo Galesi"):
                    galesi_debug["currentRowsByName"].append(row_info)
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
                    row_info = {
                        "playerUid": row.player_uid, "playerName": row.player_name,
                        "kind": kind, "clubUid": row.club_uid,
                        "clubName": row.club_name, "starts": row.starts,
                        "substituteAppearances": row.substitute_appearances,
                        "seasonYear": int(row.season_year)
                    }
                    if row.player_uid in candidate_uids:
                        galesi_debug.setdefault("archivedRowsByCandidateUid", {}).setdefault(str(row.player_uid), []).append(row_info)
                    if row.player_uid == -1:
                        galesi_debug["archivedRowsByUid"].append(row_info)
                    if row.player_uid == -2:
                        galesi_debug["archivedRowsByUniqueId"].append(row_info)
                    if norm(row.player_name) == norm("Vincenzo Galesi"):
                        galesi_debug["archivedRowsByName"].append(row_info)
                    # Les saisons antérieures à 2026/2027 ne participent plus au compteur.
                    # On conserve leur lecture uniquement pour le diagnostic fmsave.
            except Exception as exc:
                messages.append("Historique des saisons indisponible : " + type(exc).__name__)

            rows = {}
            all_keys = set(current_counts)
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
                

            try:
                for row in save.player_match_stats():
                    if row.player_uid in candidate_uids or "galesi" in norm(row.player_name):
                        target = "matchRowsByCandidateUid" if row.player_uid in candidate_uids else "matchRowsByName"
                        galesi_debug.setdefault(target, []).append({
                            "playerUid": row.player_uid, "playerName": row.player_name,
                            "date": row.date.isoformat() if row.date else None,
                            "competitionId": row.competition_id,
                            "opponent": row.opponent_club_name,
                            "minutes": row.minutes
                        })
            except Exception as exc:
                galesi_debug["matchStatsError"] = type(exc).__name__
            messages.append("Diagnostic Galesi : " + json.dumps(galesi_debug, ensure_ascii=False))
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
                "trackedClubCount": len(tracked_club_names),
                "trackedClubNames": tracked_club_names,
                "trackedClubsFound": tracked_clubs_found,
                "trackedClubsMissing": tracked_clubs_missing,
                "trackedClubUids": len(tracked_club_uids),
                "galesiDebug": galesi_debug,
                "players": sorted(rows.values(), key=lambda p: (p["name"] or "").casefold()),
                "warnings": messages
            }, ensure_ascii=False)
        finally:
            save.close()
