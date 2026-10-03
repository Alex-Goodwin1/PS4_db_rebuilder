from __future__ import print_function

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import traceback
from collections import OrderedDict
from ftplib import FTP, all_errors

import appinfo
from sfo.sfo import SfoFile

ROOT = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
TMP_DIR = os.path.join(ROOT, "tmp")
BACKUP_DIR = os.path.join(TMP_DIR, "backup")
CACHE_ROOT = os.path.join(TMP_DIR, "appmeta")
CACHE_DIR = os.path.join(CACHE_ROOT, "external")
CACHE_DIR_INT = os.path.join(CACHE_ROOT, "internal")
APP_DB = os.path.join(TMP_DIR, "app.db")
APP_DB_ORIG = os.path.join(TMP_DIR, "app.db.orig")
REPORT_FILE = os.path.join(TMP_DIR, "fix_db_report.txt")

MMS_DIR = "/system_data/priv/mms"
STORAGES = OrderedDict((
	("ext", {
		"app_dir": "/mnt/ext0/user/app",
		"meta_dirs": ("/system_data/priv/appmeta/external", "/user/appmeta/external"),
		"cache_dir": CACHE_DIR,
		"name": "external HDD",
		"hdd": "external",
	}),
	("internal", {
		"app_dir": "/user/app",
		"meta_dirs": ("/system_data/priv/appmeta", "/user/appmeta"),
		"cache_dir": CACHE_DIR_INT,
		"name": "internal HDD",
		"hdd": "internal",
	}),
))

TITLE_ID_RE = re.compile(r"^[A-Z]{4}[0-9]{5}$")
SERVICE_ID_RE = re.compile(r"-([A-Z]{4}[0-9]{5})_[0-9]{2}$")

_report = []


def log(message=""):
	_report.append(u"%s" % (message,))
	print(message)


def save_report():
	try:
		if not os.path.isdir(TMP_DIR):
			os.makedirs(TMP_DIR)
		with io.open(REPORT_FILE, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(u"\n".join(_report) + u"\n")
	except Exception as error:
		print("could not write %s: %s" % (REPORT_FILE, error))


def now_stamp():
	moment = datetime.datetime.now()
	return moment.strftime("%Y-%m-%d %H:%M:%S.") + "%03d" % (moment.microsecond // 1000)


def ensure_dirs():
	for path in [TMP_DIR, BACKUP_DIR] + [entry["cache_dir"] for entry in STORAGES.values()]:
		if not os.path.isdir(path):
			os.makedirs(path)


def storage_info(storage):
	entry = STORAGES.get(storage)
	if entry is None:
		raise SystemExit("unknown storage: %s" % storage)
	return entry


def selected_storages(args):
	if args.storage == "both":
		return list(STORAGES.keys())
	return [args.storage]


def storage_name(storage):
	return storage_info(storage)["name"]


def org_path(storage, game_id, on_disc):
	if on_disc:
		return "/mnt/disc/app/%s" % game_id
	return "%s/%s" % (storage_info(storage)["app_dir"], game_id)


def ftp_connect(args):
	ftp = FTP()
	try:
		ftp.connect(args.PS4_IP, args.port, timeout=60)
		ftp.login(user=args.user, passwd=args.password)
	except all_errors as error:
		log("cannot connect to PS4 at %s:%d -- %s" % (args.PS4_IP, args.port, error))
		log("  check that the IP is right and that GoldHEN runs its FTP server on this port")
		log("  (if the login was changed, pass --user/--password)")
		raise SystemExit(1)
	log("connected to %s:%d -> %s" % (args.PS4_IP, args.port, ftp.getwelcome()))
	return ftp


def ftp_fetch(ftp, remote_path):
	buffer = io.BytesIO()
	try:
		ftp.retrbinary("RETR %s" % remote_path, buffer.write)
	except Exception as error:
		log("    RETR %s failed: %s" % (remote_path, error))
		return None
	return buffer.getvalue()


def ftp_mlsd(ftp, remote_dir):
	try:
		return [(name, facts) for name, facts in ftp.mlsd(remote_dir)]
	except Exception as error:
		log("    MLSD %s failed: %s" % (remote_dir, error))
		return []


LIST_RE = re.compile(
	r"^(?P<type>[dl-])[rwxstST-]{9}\s+\d+\s+\S+\s+\S+\s+(?P<size>\d+)\s+\S+\s+\S+\s+(?:\d{2}:\d{2}|\d{4})\s+(?P<name>.+)$")


def ftp_list_ok(ftp, remote_dir):
	entries = ftp_mlsd(ftp, remote_dir)
	if entries:
		return [(name, {"type": facts.get("type"), "size": facts.get("size")})
			for name, facts in entries], True

	lines = []
	try:
		ftp.retrlines("LIST %s" % remote_dir, lines.append)
	except Exception as error:
		log("    LIST %s failed: %s" % (remote_dir, error))
		return [], False

	parsed = []
	for line in lines:
		match = LIST_RE.match(line.strip())
		if not match:
			continue
		kind = "dir" if match.group("type") == "d" else "file"
		parsed.append((match.group("name"), {"type": kind, "size": match.group("size")}))
	return parsed, True


def ftp_list(ftp, remote_dir):
	return ftp_list_ok(ftp, remote_dir)[0]


def ftp_dir_names(ftp, remote_dir):
	return [name for name, facts in ftp_list(ftp, remote_dir) if facts.get("type") == "dir"]


def sfo_value(sfo, key, default=None):
	if sfo is None:
		return default
	try:
		value = sfo[key]
	except Exception:
		return default
	if value is None:
		return default
	if isinstance(value, bytes):
		value = value.decode("utf-8", "replace")
	if value == "":
		return default
	return value


def sfo_int(sfo, key, default=0):
	try:
		return int(sfo_value(sfo, key, default))
	except (TypeError, ValueError):
		return default


def get_sfo(ftp, game_id, storage="ext", use_cache=True):
	data = None
	if ftp is not None:
		for folder in storage_info(storage)["meta_dirs"]:
			data = ftp_fetch(ftp, "%s/%s/param.sfo" % (folder, game_id))
			if data:
				break
	if data is None and not use_cache:
		return None

	cache_file = os.path.join(storage_info(storage)["cache_dir"], game_id, "param.sfo")
	if data is not None:
		try:
			if not os.path.isdir(os.path.dirname(cache_file)):
				os.makedirs(os.path.dirname(cache_file))
			with open(cache_file, "wb") as handle:
				handle.write(data)
		except Exception as error:
			log("    could not cache %s: %s" % (cache_file, error))
	elif os.path.isfile(cache_file):
		with open(cache_file, "rb") as handle:
			data = handle.read()

	if not data:
		return None
	try:
		return SfoFile.from_reader(io.BytesIO(data))
	except Exception as error:
		log("    param.sfo of %s is not readable: %s" % (game_id, error))
		return None


def app_json(ftp, game_id, storage="ext"):
	cache_file = os.path.join(storage_info(storage)["cache_dir"], game_id, "app.json")
	data = None
	if ftp is not None:
		raw = ftp_fetch(ftp, "%s/%s/app.json" % (storage_info(storage)["app_dir"], game_id))
		if raw is not None:
			try:
				if not os.path.isdir(os.path.dirname(cache_file)):
					os.makedirs(os.path.dirname(cache_file))
				with open(cache_file, "wb") as handle:
					handle.write(raw)
			except Exception as error:
				log("    could not cache %s: %s" % (cache_file, error))
			data = raw
	if data is None and os.path.isfile(cache_file):
		try:
			with open(cache_file, "rb") as handle:
				data = handle.read()
		except Exception as error:
			log("    could not read %s: %s" % (cache_file, error))
			return None
	if not data:
		return None
	try:
		meta = json.loads(data.decode("utf-8", "replace"))
	except Exception as error:
		log("    app.json of %s is not readable: %s" % (game_id, error))
		return None
	return meta if isinstance(meta, dict) else None


def app_json_size(meta):
	if not meta:
		return 0
	for key in ("fileSize", "originalFileSize"):
		if meta.get(key):
			try:
				return int(meta[key])
			except (TypeError, ValueError):
				pass
	total = 0
	for piece in (meta.get("pieces") or []):
		try:
			total += int(piece.get("fileSize") or 0)
		except (TypeError, ValueError):
			pass
	return total


def get_pkg_size(ftp, game_id, storage="ext"):
	app_dir = "%s/%s" % (storage_info(storage)["app_dir"], game_id)
	if ftp is not None:
		for name, facts in ftp_list(ftp, app_dir):
			if name == "app.pkg":
				try:
					return int(facts.get("size"))
				except (TypeError, ValueError):
					pass
		try:
			size = ftp.size("%s/app.pkg" % app_dir)
			if size is not None:
				return int(size)
		except Exception:
			pass
	return None


def get_app_size(ftp, game_id, storage="ext"):
	from_json = app_json_size(app_json(ftp, game_id, storage))
	from_pkg = get_pkg_size(ftp, game_id, storage)
	if storage == "internal":
		return from_json or from_pkg
	return from_pkg or from_json


def get_on_disc(ftp, game_id, storage="ext"):
	meta = app_json(ftp, game_id, storage)
	if not meta:
		return 0
	for piece in (meta.get("pieces") or []):
		if "/mnt/disc/" in (piece.get("url") or ""):
			return 1
	return 0


def storage_dir_names(ftp, storage):
	if ftp is None:
		cache_dir = storage_info(storage)["cache_dir"]
		if not os.path.isdir(cache_dir):
			return [], False
		names = [name for name in sorted(os.listdir(cache_dir))
			if TITLE_ID_RE.match(name) and os.path.isdir(os.path.join(cache_dir, name))]
		if not names:
			log("  warning: %s holds no cached game, its entries are left alone" % cache_dir)
			return names, False
		return names, True

	entries, readable = ftp_list_ok(ftp, storage_info(storage)["app_dir"])
	names = sorted(name for name, facts in entries
		if facts.get("type") == "dir" and TITLE_ID_RE.match(name))
	return names, readable


def scan_storages(ftp, args):
	found = OrderedDict()
	scanned = []
	for storage in selected_storages(args):
		names, readable = storage_dir_names(ftp, storage)
		if readable:
			scanned.append(storage)
		if ftp is not None:
			log("%-13s %d games in %s" % ("%s:" % storage_name(storage), len(names),
				storage_info(storage)["app_dir"]))
		else:
			log("offline mode, %-12s %d games taken from %s" % (
				"%s:" % storage_name(storage), len(names),
				storage_info(storage)["cache_dir"]))
		if not readable:
			log("  warning: %s could not be listed, its entries are left alone" %
				storage_info(storage)["app_dir"])
		for name in names:
			if name in found and found[name] != storage:
				log("  %s exists on the %s and on the %s -> the %s entry is used" % (
					name, storage_name(found[name]), storage_name(storage),
					storage_name(found[name])))
				continue
			found[name] = storage
	return found, scanned


def games_from_scan(found, args):
	if args.titles:
		wanted = [item.strip().upper() for item in args.titles.split(",") if item.strip()]
		primary = selected_storages(args)[0]
		picked = []
		for title_id in wanted:
			if title_id in found:
				picked.append((title_id, found[title_id]))
			else:
				log("  %s is not present in %s, but was requested" % (
					title_id, storage_info(primary)["app_dir"]))
				picked.append((title_id, primary))
		return picked
	return sorted(found.items())


def detect_games(ftp, args):
	return games_from_scan(scan_storages(ftp, args)[0], args)


META_PREFIX = OrderedDict((
	("ext", "/user/appmeta/external/"),
	("internal", "/user/appmeta/"),
))


def meta_storage(meta_data_path, storages):
	text = "%s" % (meta_data_path or "")
	for storage in storages:
		prefix = META_PREFIX[storage]
		if not text.startswith(prefix):
			continue
		rest = text[len(prefix):]
		if rest and "/" not in rest:
			return storage
	return None


def find_broken_rows(cursor, tables, args, found, scanned):
	wanted = None
	if args.titles:
		wanted = set(item.strip().upper() for item in args.titles.split(",") if item.strip())
	broken = []
	for table in tables:
		columns = table_columns(cursor, table)
		missing = [name for name in ("titleId", "metaDataPath", "onDisc")
			if name not in columns]
		if missing:
			log("  %s: no %s column, its rows are left alone" % (table, ", ".join(missing)))
			continue
		cursor.execute("SELECT titleId, titleName, metaDataPath, onDisc FROM [%s];" % table)
		for row in cursor.fetchall():
			title_id = "%s" % (row[0] or "")
			storage = meta_storage(row[2], scanned)
			if not TITLE_ID_RE.match(title_id) or title_id in found or storage is None:
				continue
			if title_id.startswith("NPXS") or row[3]:
				continue
			if wanted is not None and title_id not in wanted:
				continue
			broken.append((table, title_id, "%s" % (row[1] or title_id), storage))
	return broken


def report_broken(broken, args, scanned):
	by_id = OrderedDict()
	for table, title_id, title_name, storage in broken:
		entry = by_id.setdefault(title_id, [title_name, storage, 0])
		entry[2] += 1
	log("broken rows: %d title id(s), %d row(s) - no game folder on %s:" % (
		len(by_id), len(broken), ", ".join(storage_name(item) for item in scanned)))
	for title_id in by_id:
		title_name, storage, count = by_id[title_id]
		log("  %-10s %-28s %-14s %d row(s)" % (title_id, title_name,
			storage_name(storage), count))
	if not args.prune:
		log("  nothing was deleted, run it again with --prune to remove these rows")


def prune_broken(cursor, broken, args):
	rows = 0
	title_ids = []
	tables = []
	for table, title_id, title_name, storage in broken:
		cursor.execute("DELETE FROM [%s] WHERE titleId=?;" % table, (title_id,))
		rows += max(cursor.rowcount or 0, 0)
		if title_id not in title_ids:
			title_ids.append(title_id)
		if table not in tables:
			tables.append(table)
	appinfo_rows = 0
	if not args.no_appinfo and table_exists(cursor, "tbl_appinfo"):
		for title_id in title_ids:
			cursor.execute("DELETE FROM tbl_appinfo WHERE titleId=?;", (title_id,))
			appinfo_rows += max(cursor.rowcount or 0, 0)
	return rows, appinfo_rows, title_ids, tables


def table_exists(cursor, name):
	cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
	return cursor.fetchone() is not None


def verify_prune(cursor, tables, title_ids, check_appinfo=True):
	left = []
	for table in tables:
		for title_id in title_ids:
			cursor.execute("SELECT 1 FROM [%s] WHERE titleId=?;" % table, (title_id,))
			if cursor.fetchone():
				left.append("%s: %s" % (table, title_id))
	appinfo_rows = 0
	if table_exists(cursor, "tbl_appinfo"):
		for title_id in title_ids:
			cursor.execute("SELECT COUNT(*) FROM tbl_appinfo WHERE titleId=?;", (title_id,))
			appinfo_rows += cursor.fetchone()[0]
	cursor.execute("PRAGMA integrity_check;")
	check = cursor.fetchone()[0]
	log("")
	log("prune verification: %d title id(s) removed, %d row(s) left, %d tbl_appinfo "
		"row(s) left, integrity_check=%s" % (len(title_ids), len(left), appinfo_rows, check))
	for item in left[:5]:
		log("  still in app.db: %s" % item)
	if not check_appinfo:
		appinfo_rows = 0
	return not left and not appinfo_rows and check == "ok"


def browse_category(sfo):
	category = sfo_value(sfo, "CATEGORY", "gd")
	if category == "gp":
		category = "gd"
	return category


def resolve_title_key(option, locale):
	if option in (None, "", "auto"):
		if locale:
			return "TITLE_%02d" % locale
		return "TITLE"
	if option in ("none", "off", "title"):
		return "TITLE"
	digits = "".join([char for char in str(option) if char.isdigit()])
	if not digits:
		return "TITLE"
	return "TITLE_%02d" % int(digits)


def browse_title(sfo, game_id, title_key="TITLE"):
	for key in ((title_key, "TITLE") if title_key != "TITLE" else ("TITLE",)):
		title = sfo_value(sfo, key)
		if title and title.strip():
			return title
	return game_id


def browse_service_id(sfo, key):
	value = sfo_value(sfo, key)
	if not value or not str(value).strip():
		return None
	text = str(value).strip()
	if TITLE_ID_RE.match(text):
		return text
	match = SERVICE_ID_RE.search(text)
	if match:
		return match.group(1)
	return None


def build_browse_row(game_id, sfo, size, on_disc, hdd_location, access_index, now,
		title_key="TITLE", meta_data_path=None):
	category = browse_category(sfo)
	ui_category = "game" if category in ("gd", "gp", "gde", "gda") else "app"
	return OrderedDict((
		("titleId", game_id),
		("contentId", sfo_value(sfo, "CONTENT_ID")),
		("titleName", browse_title(sfo, game_id, title_key)),
		("metaDataPath", meta_data_path or "/user/appmeta/external/%s" % game_id),
		("lastAccessTime", now),
		("contentStatus", 0),
		("onDisc", on_disc),
		("parentalLevel", sfo_int(sfo, "PARENTAL_LEVEL", 1)),
		("visible", 1),
		("sortPriority", 100),
		("pathInfo", 0),
		("lastAccessIndex", access_index),
		("dispLocation", 5),
		("canRemove", 1),
		("category", category),
		("contentType", 0),
		("pathInfo2", 0),
		("presentBoxStatus", 0),
		("entitlement", 0),
		("thumbnailUrl", None),
		("lastUpdateTime", None),
		("playableDate", None),
		("contentSize", int(size or 0)),
		("installDate", now),
		("platform", 0),
		("uiCategory", ui_category),
		("skuId", None),
		("disableLiveDetail", 0),
		("linkType", 0),
		("linkUri", None),
		("serviceIdAddCont1", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_1")),
		("serviceIdAddCont2", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_2")),
		("serviceIdAddCont3", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_3")),
		("serviceIdAddCont4", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_4")),
		("serviceIdAddCont5", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_5")),
		("serviceIdAddCont6", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_6")),
		("serviceIdAddCont7", browse_service_id(sfo, "SERVICE_ID_ADDCONT_ADD_7")),
		("folderType", 0),
		("folderInfo", None),
		("parentFolderId", None),
		("positionInFolder", None),
		("activeDate", None),
		("entitlementTitleName", None),
		("hddLocation", int(hdd_location)),
		("externalHddAppStatus", 0),
		("entitlementIdKamaji", None),
		("mTime", now),
		("freePsPlusContent", 0),
		("entitlementActiveFlag", 0),
		("sizeOtherHdd", 0),
		("entitlementHidden", 0),
		("preorderPlaceholderFlag", 0),
		("gatingEntitlementJson", None),
		("entitlementStatusServiceType", 0),
		("creationDate", None),
		("purchasedDate", None),
		("entitlementRewardMembershipType", None),
	))


def table_columns(cursor, table):
	cursor.execute("PRAGMA table_info([%s]);" % table)
	return set(row[1] for row in cursor.fetchall())


def appbrowse_tables(cursor):
	cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tbl_appbrowse_%' ORDER BY name;")
	return [row[0] for row in cursor.fetchall()]


def get_tbl_version(cursor):
	cursor.execute("SELECT category, status FROM tbl_version;")
	values = {}
	for category, status in cursor.fetchall():
		if category is None:
			continue
		values[str(category)] = status
	return values


def version_int(version, key, default=0):
	try:
		return int(version.get(key, default))
	except (TypeError, ValueError):
		return default


def insert_row(cursor, table, columns, values, dry_run=False):
	keys = [key for key in values if key in columns]
	missing = [key for key in values if key not in columns]
	sql = "INSERT INTO [%s] (%s) VALUES (%s);" % (
		table, ", ".join("[%s]" % key for key in keys), ", ".join("?" * len(keys)))
	if dry_run:
		return sql, keys, missing
	cursor.execute(sql, [values[key] for key in keys])
	return sql, keys, missing


def repair_row(cursor, table, columns, values):
	changes = {}
	for column in ("hddLocation", "metaDataPath"):
		if column not in columns:
			continue
		row = cursor.execute("SELECT [%s] FROM [%s] WHERE titleId=?;" % (column, table),
			(values["titleId"],)).fetchone()
		if row is None or row[0] == values.get(column):
			continue
		changes[column] = values[column]
	if not changes:
		return None
	sql = "UPDATE [%s] SET %s WHERE titleId=?;" % (
		table, ", ".join("[%s]=?" % key for key in changes))
	cursor.execute(sql, list(changes.values()) + [values["titleId"]])
	return sql


def prepare_db(ftp, args):
	if args.db:
		local = os.path.abspath(args.db)
		if not os.path.isfile(local):
			raise SystemExit("local app.db not found: %s" % local)
		if os.path.abspath(local) != os.path.abspath(APP_DB):
			shutil.copy2(local, APP_DB)
		log("working on the local app.db: %s" % APP_DB)
		return APP_DB

	data = ftp_fetch(ftp, "%s/app.db" % MMS_DIR)
	if not data:
		raise SystemExit("could not download %s/app.db" % MMS_DIR)

	with open(APP_DB_ORIG, "wb") as handle:
		handle.write(data)
	log("downloaded %s/app.db: %d bytes" % (MMS_DIR, len(data)))
	if not args.no_backup:
		stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
		backup = os.path.join(BACKUP_DIR, "app.db.%s" % stamp)
		shutil.copy2(APP_DB_ORIG, backup)
		log("backup of the original: %s" % backup)
	shutil.copy2(APP_DB_ORIG, APP_DB)
	return APP_DB


def upload_db(ftp, local_path):
	log("uploading %s -> %s/app.db ..." % (local_path, MMS_DIR))
	ftp.cwd(MMS_DIR)
	with open(local_path, "rb") as handle:
		ftp.storbinary("STOR app.db", handle)
	log("upload finished (%d bytes)" % os.path.getsize(local_path))

	with open(local_path, "rb") as handle:
		mine = hashlib.md5(handle.read()).hexdigest()
	remote = ftp_fetch(ftp, "%s/app.db" % MMS_DIR)
	if remote is None:
		log("  warning: could not read app.db back for the md5 check")
	elif hashlib.md5(remote).hexdigest() == mine:
		log("md5 check after upload: OK (%s)" % mine)
	else:
		log("  WARNING: app.db on the PS4 does not match the local file, upload again!")


def gather_registrations(ftp, games, version, now, args, title_key="TITLE"):
	ext_hdd_id = version_int(version, "external_hdd_id", 0)
	access_index = version_int(version, "access_index", 0)
	update_index = version_int(version, "update_index", 0)
	on_disc = None if args.on_disc == "auto" else int(args.on_disc)

	registrations = []
	for game_id, storage in games:
		sfo = get_sfo(ftp, game_id, storage)
		if sfo is None:
			log("  %s [%s]: no param.sfo readable -> skipped" % (game_id, storage))
			continue

		title_id = sfo_value(sfo, "TITLE_ID", game_id)
		if title_id != game_id:
			log("  %s: warning, param.sfo says TITLE_ID=%s" % (game_id, title_id))

		hdd_location = 0 if storage == "internal" else ext_hdd_id
		meta_data_path = "/user/appmeta/%s" % game_id if storage == "internal" \
			else "/user/appmeta/external/%s" % game_id

		size = get_app_size(ftp, game_id, storage)
		if not size:
			log("  %s: warning, size unknown, contentSize will be 0" % game_id)

		game_on_disc = on_disc if on_disc is not None else get_on_disc(ftp, game_id, storage)
		access_index += 1
		row = build_browse_row(game_id, sfo, size, game_on_disc, hdd_location,
			access_index, now, title_key=title_key, meta_data_path=meta_data_path)
		items = appinfo.get_pseudo_appinfo(
			sfo, size, hdd_location=hdd_location, access_index=access_index,
			update_index=update_index, now=now, on_disc=game_on_disc,
			external_hdd=(storage == "ext"), meta_data_path=meta_data_path,
			org_path=org_path(storage, game_id, game_on_disc),
			disc_copy_type=2 if (storage == "internal" and game_on_disc) else None)
		registrations.append((game_id, row, items))
		log("  %s [%s]: %s | %s | %d bytes | onDisc=%d | lastAccessIndex=%d" % (
			game_id, storage, row["titleName"], row["category"], row["contentSize"],
			row["onDisc"], access_index))
	return registrations


def register_browse(cursor, tables, columns_by_table, registrations, args):
	ids = [entry[0] for entry in registrations]
	example = None
	for table in tables:
		columns = columns_by_table[table]
		cursor.execute("SELECT titleId FROM [%s];" % table)
		known = set(row[0] for row in cursor.fetchall())
		inserted = 0
		repaired = 0
		for game_id, row, items in registrations:
			if game_id in known:
				if args.repair:
					sql = repair_row(cursor, table, columns, row)
					if sql:
						repaired += 1
						log("    %s: repaired %s" % (table, game_id))
						if example is None:
							example = (table, sql, None, None, row)
				continue
			sql, keys, missing = insert_row(cursor, table, columns, row)
			inserted += 1
			if example is None:
				example = (table, sql, keys, missing, row)
		log("  %-32s columns=%2d added=%d repaired=%d" % (table, len(columns), inserted, repaired))

	if example is not None:
		table, sql, keys, missing, row = example
		log("")
		log("example SQL for %s:" % table)
		log("  %s" % sql)
		for key in (keys or []):
			log("    %-32s = %r" % (key, row[key]))
		if missing:
			log("  columns of tbl_appbrowse not present in this table: %s" % ", ".join(missing))
	return ids


def register_appinfo(cursor, registrations, args):
	cursor.execute("SELECT titleId, key FROM tbl_appinfo;")
	known = set((str(row[0]), str(row[1])) for row in cursor.fetchall())
	added = 0
	for game_id, row, items in registrations:
		missing = 0
		for key in sorted(items.keys()):
			if (game_id, key) in known:
				continue
			cursor.execute("INSERT INTO tbl_appinfo (titleId, key, val) VALUES (?, ?, ?);",
				(game_id, key, items[key]))
			missing += 1
			added += 1
		log("  appinfo %s: %d keys added" % (game_id, missing))
	return added


def known_games(cursor, tables):
	known = set()
	for table in tables:
		cursor.execute("SELECT titleId FROM [%s];" % table)
		known.update(str(row[0]) for row in cursor.fetchall() if row[0] is not None)
	return known


def verify(cursor, tables, registrations, version):
	ids = [entry[0] for entry in registrations]
	expected = dict((entry[0], entry[1]["hddLocation"]) for entry in registrations)
	placeholders = ", ".join("?" * len(ids))
	problems = []
	for table in tables:
		cursor.execute("SELECT titleId, hddLocation FROM [%s];" % table)
		actual = dict((str(row[0]), row[1]) for row in cursor.fetchall())
		wrong = []
		for game_id, wanted in sorted(expected.items()):
			if game_id not in actual:
				wrong.append("%s has no row" % game_id)
			elif int(actual[game_id] or 0) != int(wanted or 0):
				wrong.append("%s has hddLocation=%s, expected %s" % (
					game_id, actual[game_id], wanted))
		if wrong:
			problems.append("%s: %d of %d rows wrong (%s)" % (
				table, len(wrong), len(ids), "; ".join(wrong[:5])))
	cursor.execute("SELECT COUNT(*) FROM tbl_appinfo WHERE titleId IN (%s);" % placeholders, ids)
	appinfo_rows = cursor.fetchone()[0]
	cursor.execute("PRAGMA integrity_check;")
	check = cursor.fetchone()[0]
	internal = len([entry for entry in registrations if not entry[1]["hddLocation"]])
	log("")
	log("verification: %d games (%d internal, %d external), tbl_appbrowse rows %s, "
		"tbl_appinfo rows %d, integrity_check=%s" % (len(ids), internal, len(ids) - internal,
		"OK" if not problems else "INCOMPLETE", appinfo_rows, check))
	for problem in problems:
		log("  %s" % problem)
	return not problems and check == "ok"


def parse_args(argv=None):
	parser = argparse.ArgumentParser(
		description="add the games of a PS4 (external HDD ext0 / internal HDD) to app.db")
	parser.add_argument("PS4_IP", nargs="?", default=None, help="address of the PS4, required unless --db is used")
	parser.add_argument("--port", type=int, default=2121, help="FTP port (GoldHEN uses 2121)")
	parser.add_argument("--user", default="username", help="FTP user")
	parser.add_argument("--password", default="password", help="FTP password")
	parser.add_argument("--storage", default="both", choices=("both", "ext", "internal"),
		help="where to look for games: ext = /mnt/ext0/user/app (external HDD), "
			"internal = /user/app (HDD of the console), both = external HDD first, a "
			"title id found on both plug-ins is taken from ext0 (default: both)")
	parser.add_argument("--apply", action="store_true",
		help="upload the fixed app.db back to the PS4 (without it nothing is written to the console)")
	parser.add_argument("--yes", action="store_true", help="do not ask before uploading")
	parser.add_argument("--titles", default=None, metavar="ID,ID",
		help="only these title ids, e.g. CUSA00001,CUSA00002")
	parser.add_argument("--db", default=None, metavar="FILE",
		help="use this local app.db instead of downloading one")
	parser.add_argument("--offline", action="store_true",
		help="no FTP at all (needs --db, param.sfo comes from the tmp cache)")
	parser.add_argument("--no-appinfo", action="store_true", help="do not touch tbl_appinfo")
	parser.add_argument("--no-backup", action="store_true", help="do not copy app.db to tmp/backup")
	parser.add_argument("--repair", action="store_true",
		help="also fix hddLocation/metaDataPath of rows that exist already (pathInfo and "
			"other values PS4 wrote itself stay untouched)")
	parser.add_argument("--prune", action="store_true",
		help="delete the rows of games whose folder is gone: metaDataPath points into a "
			"scanned storage and no /app/<TITLE_ID> was found there; NPXS rows, onDisc=1 "
			"rows and rows of a storage that could not be listed are kept")
	parser.add_argument("--on-disc", default="auto", choices=("auto", "0", "1"),
		help="onDisc value, auto = 1 when the game was installed from /mnt/disc")
	parser.add_argument("--title-lang", default="auto", metavar="NN",
		help="param.sfo key used for tbl_appbrowse.titleName; auto = the locale of the "
			"console (tbl_version.locale, e.g. 08 = Russian), NN = force TITLE_NN, "
			"none = plain TITLE; TITLE is the fallback when TITLE_NN is missing")
	parser.add_argument("--restore", default=None, metavar="FILE",
		help="upload FILE to the PS4 as app.db and exit")
	return parser.parse_args(argv)


def confirm(args):
	if args.yes or not sys.stdin.isatty():
		return True
	try:
		answer = input("write app.db to the PS4 now? [y/N] ")
	except (EOFError, KeyboardInterrupt):
		return False
	return answer.strip().lower() in ("y", "yes", "j", "ja", "д", "да")


def run(args):
	ftp = None
	try:
		if args.restore and args.offline:
			raise SystemExit("--restore cannot be used together with --offline")
		if not args.offline:
			ftp = ftp_connect(args)

		if args.restore:
			if not confirm(args):
				log("restore cancelled")
				return 1
			upload_db(ftp, os.path.abspath(args.restore))
			return 0

		found, scanned = scan_storages(ftp, args)
		games = games_from_scan(found, args)
		if not games:
			log("no game folder found")
			if not args.prune:
				log("nothing to do")
				return 0

		local_db = prepare_db(ftp, args)
		conn = sqlite3.connect(local_db)
		try:
			cursor = conn.cursor()
			version = get_tbl_version(cursor)
			hdd_id = version_int(version, "external_hdd_id", 0)
			log("tbl_version: external_hdd_id=%d access_index=%d update_index=%d" % (hdd_id,
				version_int(version, "access_index", 0), version_int(version, "update_index", 0)))
			if not hdd_id and "ext" in selected_storages(args):
				log("  warning: external_hdd_id is 0/unknown, external HDD entries would "
					"look like internal ones")

			tables = appbrowse_tables(cursor)
			columns_by_table = dict((table, table_columns(cursor, table)) for table in tables)
			if tables:
				log("tbl_appbrowse tables: %d (columns %d .. %d)" % (len(tables),
					min(len(cols) for cols in columns_by_table.values()),
					max(len(cols) for cols in columns_by_table.values())))
			else:
				log("warning: no tbl_appbrowse_* table found, the DB layout is unknown")

			now = now_stamp()
			title_key = resolve_title_key(args.title_lang, version_int(version, "locale", 0))
			log("titleName comes from param.sfo key %s (--title-lang %s)" % (
				title_key, args.title_lang))
			log("")

			known = known_games(cursor, tables) if tables else set()
			for storage in selected_storages(args):
				on_storage = [game for game in games if game[1] == storage]
				have = len([1 for game in on_storage if game[0] in known])
				log("%-15s %d game(s), %d already in app.db" % (
					"%s:" % storage_name(storage), len(on_storage), have))
			skipped = [game[0] for game in games if game[0] in known]
			if skipped:
				log("%d game(s) skipped, a row exists already (--repair touches them):" % len(skipped))
				log("  %s" % ", ".join(skipped))

			broken = []
			if args.prune and tables:
				if found:
					broken = find_broken_rows(cursor, tables, args, found, scanned)
				else:
					log("")
					log("warning: no game was found on the scanned storages, --prune skipped")
			if broken:
				log("")
				report_broken(broken, args, scanned)

			games_to_register = [game for game in games if game[0] not in known]
			if args.repair or not tables:
				games_to_register = list(games)
			if not games_to_register and not broken:
				log("")
				log("nothing to do: every game found on the PS4 is already in app.db")
				return 0

			registrations = []
			if games_to_register:
				log("")
				log("games to register: %d" % len(games_to_register))
				registrations = gather_registrations(ftp, games_to_register, version, now,
					args, title_key)
				if not registrations:
					log("no game could be registered (no readable param.sfo)")
					if not broken:
						return 1

			pruned = []
			pruned_tables = []
			if registrations or (broken and args.prune):
				log("")
				log("updating app.db ...")
			if broken and args.prune:
				rows, appinfo_rows, pruned, pruned_tables = prune_broken(cursor, broken, args)
				log("  deleted %d browse row(s) and %d tbl_appinfo row(s) of %d game(s)" % (
					rows, appinfo_rows, len(pruned)))
			if registrations:
				register_browse(cursor, tables, columns_by_table, registrations, args)
				if args.no_appinfo:
					log("tbl_appinfo: skipped (--no-appinfo)")
				else:
					log("tbl_appinfo:")
					register_appinfo(cursor, registrations, args)
			conn.commit()
			ok = True
			if registrations:
				ok = verify(cursor, tables, registrations, version)
			if pruned:
				ok = verify_prune(cursor, pruned_tables, pruned, not args.no_appinfo) and ok
		finally:
			conn.close()

		if not ok:
			log("")
			log("local app.db is incomplete, upload skipped")
			return 1

		if args.apply and ftp is None:
			log("")
			log("offline mode, nothing was uploaded")
			log("  fixed DB        : %s" % local_db)
			log("  original app.db : %s" % APP_DB_ORIG)
			log("  upload it with  : fix_db.exe %s --db %s --apply" % (
				args.PS4_IP or "PS4_IP", local_db))
			return 0

		if args.apply:
			if not confirm(args):
				log("upload cancelled, the fixed DB stays in %s" % local_db)
				return 1
			log("")
			upload_db(ftp, local_db)
			log("")
			log("done. Log the PS4 user out (or reboot) so PS4 reads app.db again.")
		else:
			log("")
			log("dry run finished, nothing was written to the PS4")
			log("  fixed DB        : %s" % local_db)
			log("  original app.db : %s" % APP_DB_ORIG)
			log("  upload it with  : fix_db.exe %s --apply%s" % (args.PS4_IP or "PS4_IP",
				"" if args.storage == "both" else " --storage %s" % args.storage))
		return 0
	finally:
		if ftp is not None:
			try:
				ftp.quit()
			except Exception:
				try:
					ftp.close()
				except Exception:
					pass


def main(argv=None):
	args = parse_args(argv)
	ensure_dirs()
	if args.PS4_IP is None and not args.offline:
		raise SystemExit("usage: fix_db.exe PS4_IP [--apply]    (offline: --offline --db tmp/app.db)")
	code = 1
	try:
		code = run(args)
	except SystemExit:
		raise
	except Exception:
		log("ERROR:")
		log(traceback.format_exc())
	finally:
		save_report()
	return code


if __name__ == "__main__":
	try:
		sys.stdout.reconfigure(errors="replace")
	except Exception:
		pass
	sys.exit(main())
