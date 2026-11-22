import json
import unicodedata
import warnings
import sys
import fmsave
import fmsave._container as fmsave_container

# Pyodide tourne en WebAssembly 32 bits : zstandard attend un max_length
# compatible avec Py_ssize_t. Les limites proportionnelles de fmsave peuvent
# dépasser 2 Go même lorsque la trame réellement décompressée est plus petite.
if sys.platform == "emscripten":
    _original_decompress_frame = fmsave_container.decompress_frame

    def _wasm_safe_decompress_frame(
        compressed, *, expected_size, cap, what, file_name, overrun=None
    ):
        cap = min(cap, sys.maxsize - 1)
        return _original_decompress_frame(
            compressed,
            expected_size=expected_size,
            cap=cap,
            what=what,
            file_name=file_name,
            overrun=overrun,
        )

    fmsave_container.decompress_frame = _wasm_safe_decompress_frame

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()

TRACKED_CLUBS = [
    {"name": "AC Libertas", "unique_id": 1301141},
    {"name": "FC Domagnano", "unique_id": 1301125},
    {"name": "FC Fiorentino", "unique_id": 8800000},
    {"name": "SS Folgore/Falciano", "unique_id": 1301131},
    {"name": "AC Juvenes-Dogana", "unique_id": 1301142},
    {"name": "La Fiorita 1967", "unique_id": 1301129},
    {"name": "SS Pennarossa", "unique_id": 8800002},
    {"name": "SS San Giovanni", "unique_id": 1301135},
    {"name": "San Marino Academy", "unique_id": 60021565},
    {"name": "SC Faetano", "unique_id": 1301127},
    {"name": "SP Cailungo", "unique_id": 1301121},
    {"name": "SS Cosmos", "unique_id": 1301123},
    {"name": "SS Murata", "unique_id": 1301133},
    {"name": "Tre Fiori", "unique_id": 1301137},
    {"name": "SP Tre Penne", "unique_id": 8800001},
    {"name": "SS Virtus", "unique_id": 1301139},
    {"name": "San Marino Calcio", "unique_id": 2000113410}
]

TRACKED_BY_ID = {club["unique_id"]: club["name"] for club in TRACKED_CLUBS}

def club_unique_id(club):
    value = getattr(club, "unique_id", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def appearances(row):
    return int(row.starts or 0) + int(row.substitute_appearances or 0)

def analyze_save(path, tracked_json, tracked_player_history_json="{}"):
    # Les identifiants uniques fournis par l'utilisateur sont la référence.
    # Les noms de clubs et la configuration Firebase ne servent plus à la détection.
    tracked_names = [club["name"] for club in TRACKED_CLUBS]
    tracked_ids = set(TRACKED_BY_ID)
    messages = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        save = fmsave.open(path)
        try:
            info = save.info
            # Les joueurs stockent un nation_id local à la sauvegarde.
            # save.nations() permet de le convertir en database_id FM stable.
            nation_database_ids = {
                int(nation.nation_id): int(nation.database_id)
                for nation in save.nations()
                if nation.nation_id is not None and nation.database_id is not None
            }
            def database_nation_id(local_id):
                if local_id is None:
                    return None
                try:
                    return nation_database_ids.get(int(local_id))
                except (TypeError, ValueError):
                    return None
            players = list(save.players())
            nation_player_counts = {}
            for player in players:
                for local_nation_id in [player.nation_id, *(player.second_nation_ids or ())]:
                    if local_nation_id is not None:
                        try:
                            key = int(local_nation_id)
                            nation_player_counts[key] = nation_player_counts.get(key, 0) + 1
                        except (TypeError, ValueError):
                            pass
            nation_map = [{
                "localId": int(nation.nation_id),
                "databaseId": int(nation.database_id),
                "players": nation_player_counts.get(int(nation.nation_id), 0)
            } for nation in save.nations()
              if nation.nation_id is not None and nation.database_id is not None]
            nation_map.sort(key=lambda item: (item["databaseId"], item["localId"]))
            clubs = list(save.clubs())
            player_by_uid = {p.uid: p for p in players}
            club_by_uid = {c.uid: c for c in clubs}
            clubs_by_unique_id = {
                club_unique_id(c): c for c in clubs
                if club_unique_id(c) in tracked_ids
            }
            tracked_club_uids = {c.uid for c in clubs if club_unique_id(c) in tracked_ids}
            tracked_clubs_found = [
                TRACKED_BY_ID[unique_id] for unique_id in TRACKED_BY_ID
                if unique_id in clubs_by_unique_id
            ]
            tracked_club_names = [club["name"] for club in TRACKED_CLUBS]
            tracked_clubs_missing = [
                club["name"] for club in TRACKED_CLUBS
                if club["unique_id"] not in clubs_by_unique_id
            ]
            tracked_club_matches = [{
                "name": TRACKED_BY_ID[unique_id],
                "saveName": club.name,
                "uniqueId": unique_id,
                "uid": club.uid
            } for unique_id, club in clubs_by_unique_id.items()]
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

            # Audit par club : apparitions agrégées par joueur et club.
            club_audit = {
                club_uid: {
                    "name": club.name,
                    "uid": club_uid,
                    "uniqueId": club_unique_id(club),
                    "players": set(),
                    "appearances": 0,
                    "statRows": 0
                }
                for club_uid, club in club_by_uid.items()
                if club_unique_id(club) in tracked_ids
            }
            for row in current_stats:
                kind = getattr(row.kind, "name", str(row.kind)).casefold().rsplit(".", 1)[-1]
                if not ("league" in kind or "cup" in kind or "continental" in kind):
                    continue
                audit = club_audit.get(row.club_uid)
                if audit is None or row.player_uid is None or row.player_uid < 0:
                    continue
                audit["players"].add(row.player_uid)
                audit["appearances"] += appearances(row)
                audit["statRows"] += 1
            club_audit_output = [{
                "name": item["name"],
                "uid": item["uid"],
                "uniqueId": item["uniqueId"],
                "players": len(item["players"]),
                "appearances": item["appearances"],
                "statRows": item["statRows"]
            } for item in sorted(club_audit.values(), key=lambda x: norm(x["name"]))]
            player_clubs = {}
            for (uid, club_uid), count in current_counts.items():
                if uid is None or uid < 0 or count <= 0:
                    continue
                player_clubs.setdefault(uid, {})[club_uid] = count
            multi_club_players = []
            for uid, club_counts in player_clubs.items():
                if len(club_counts) < 2:
                    continue
                player = player_by_uid.get(uid)
                multi_club_players.append({
                    "uid": uid,
                    "name": player.name if player else None,
                    "clubs": [{
                        "name": club_by_uid[club_uid].name if club_uid in club_by_uid else "Club non identifié",
                        "appearances": count
                    } for club_uid, count in club_counts.items()],
                    "totalAppearances": sum(club_counts.values())
                })
            multi_club_players.sort(key=lambda item: (item["name"] or "").casefold())

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
            excluded_sammarinese_uids = set()
            try:
                tracked_player_history = json.loads(tracked_player_history_json or "{}")
            except (TypeError, ValueError):
                tracked_player_history = {}
            all_keys = set(current_counts)
            for uid, player in player_by_uid.items():
                if player.club_uid in tracked_club_uids:
                    all_keys.add((uid, player.club_uid))
            for uid, club_uid in all_keys:
                player = player_by_uid.get(uid)
                club_name = (
                    current_clubs.get((uid, club_uid))
                    or archived_clubs.get((uid, club_uid))
                    or (player.club_name if player and player.club_uid == club_uid else None)
                    or (club_by_uid[club_uid].name if club_uid in club_by_uid else "Club non identifié")
                )
                if club_uid not in tracked_club_uids:
                    continue
                key = str(uid)
                if key not in rows:
                    rows[key] = {
                        "uid": uid,
                        "name": player.name if player else None,
                        "currentClub": player.club_name if player else None,
                        "currentClubUid": player.club_uid if player else None,
                        "databaseNationId": database_nation_id(player.nation_id) if player else None,
                        "secondDatabaseNationIds": [value for value in (database_nation_id(n) for n in (player.second_nation_ids or ())) if value is not None] if player else [],
                        "clubs": [],
                        "currentSeasonAppearances": 0,
                        "archivedAppearances": 0,
                        "archivedSeasons": []
                    }
                entry = rows[key]
                if club_name and club_name not in entry["clubs"]:
                    entry["clubs"].append(club_name)
                entry["currentSeasonAppearances"] += current_counts.get((uid, club_uid), 0)

            # Réintégrer les joueurs déjà suivis dans Firebase, même s'ils ont quitté
            # les clubs saint-marinais. Leur club actuel vient de la sauvegarde si disponible.
            for uid_text, saved_player in tracked_player_history.items():
                try:
                    uid = int(uid_text)
                except (TypeError, ValueError):
                    continue
                key = str(uid)
                player = player_by_uid.get(uid)
                saved_nation_ids = [saved_player.get("databaseNationId")]
                saved_nation_ids.extend(saved_player.get("secondDatabaseNationIds") or [])
                current_nation_ids = (
                    [database_nation_id(player.nation_id)]
                    + [database_nation_id(n) for n in (player.second_nation_ids or ())]
                ) if player else []
                if 792 in saved_nation_ids or 792 in current_nation_ids:
                    excluded_sammarinese_uids.add(key)
                    continue
                if key not in rows:
                    rows[key] = {
                        "uid": uid,
                        "name": (player.name if player else None) or saved_player.get("name"),
                        "currentClub": player.club_name if player else saved_player.get("currentClub"),
                        "currentClubUid": player.club_uid if player else None,
                        "databaseNationId": database_nation_id(player.nation_id) if player else saved_player.get("databaseNationId"),
                        "secondDatabaseNationIds": [value for value in (database_nation_id(n) for n in (player.second_nation_ids or ())) if value is not None] if player else saved_player.get("secondDatabaseNationIds", []),
                        "clubs": [],
                        "currentSeasonAppearances": 0,
                        "archivedAppearances": 0,
                        "archivedSeasons": []
                    }
                entry = rows[key]
                if player:
                    entry["name"] = player.name or entry["name"]
                    entry["currentClub"] = player.club_name or entry["currentClub"]
                    entry["currentClubUid"] = player.club_uid
                    entry["databaseNationId"] = database_nation_id(player.nation_id)
                    entry["secondDatabaseNationIds"] = [value for value in (database_nation_id(n) for n in (player.second_nation_ids or ())) if value is not None]
                for club_name in saved_player.get("clubs", []):
                    if club_name and club_name not in entry["clubs"]:
                        entry["clubs"].append(club_name)
                

            # Exclure définitivement du suivi actif les joueurs déjà saint-marinais
            # (nationalité principale ou secondaire, ID base FM27 792).
            excluded_sammarinese_uids.update(
                str(uid) for uid in tracked_player_history.get("_excludedSammarineseUids", [])
            )
            for uid_text, entry in list(rows.items()):
                nation_ids = [entry.get("databaseNationId")]
                nation_ids.extend(entry.get("secondDatabaseNationIds") or [])
                if 792 in nation_ids:
                    excluded_sammarinese_uids.add(str(uid_text))
                    rows.pop(uid_text, None)
            for uid_text in excluded_sammarinese_uids:
                rows.pop(str(uid_text), None)

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
                "nationMap": nation_map,
                "trackedClubCount": len(tracked_club_names),
                "trackedClubNames": tracked_club_names,
                "trackedClubsFound": tracked_clubs_found,
                "trackedClubsMissing": tracked_clubs_missing,
                "trackedClubMatches": tracked_club_matches,
                "trackedClubUniqueIds": sorted(tracked_ids),
                "trackedClubUids": len(tracked_club_uids),
                "clubAudit": club_audit_output,
                "multiClubPlayers": multi_club_players,
                "galesiDebug": galesi_debug,
                "excludedSammarinesePlayers": len([
                    uid for uid in player_by_uid
                    if database_nation_id(player_by_uid[uid].nation_id) == 792
                    or 792 in [value for value in (database_nation_id(n) for n in (player_by_uid[uid].second_nation_ids or ())) if value is not None]
                ]),
                "excludedPlayerUids": sorted(excluded_sammarinese_uids),
                "players": sorted(rows.values(), key=lambda p: (p["name"] or "").casefold()),
                "warnings": messages
            }, ensure_ascii=False)
        finally:
            save.close()
