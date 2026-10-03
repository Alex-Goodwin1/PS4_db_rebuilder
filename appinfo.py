from __future__ import print_function

_SFO_SKIP = ("DEV_FLAG", "PUBTOOLINFO", "PUBTOOLVER", "PUBTOOLMINVER")

_APPINFO_STATIC = {
	"#_contents_status": 0,
	"#exit_type": 0,
	"ATTRIBUTE_INTERNAL": 0,
	"DISP_LOCATION_1": 0,
	"DISP_LOCATION_2": 0,
	"FORMAT": "obs",
	"DOWNLOAD_DATA_SIZE": 0,
	"PT_PARAM": 0,
	"SELF_2MIB_PAGE_AMOUNT": 0,
	"SERVICE_ID_ADDCONT_ADD_1": 0,
	"SERVICE_ID_ADDCONT_ADD_2": 0,
	"SERVICE_ID_ADDCONT_ADD_3": 0,
	"SERVICE_ID_ADDCONT_ADD_4": 0,
	"SERVICE_ID_ADDCONT_ADD_5": 0,
	"SERVICE_ID_ADDCONT_ADD_6": 0,
	"SERVICE_ID_ADDCONT_ADD_7": 0,
	"USER_DEFINED_PARAM_1": 0,
	"USER_DEFINED_PARAM_2": 0,
	"USER_DEFINED_PARAM_3": 0,
	"USER_DEFINED_PARAM_4": 0,
	"_current_slot": 0,
	"_disable_live_detail": 0,
	"_path_info": 0,
	"_path_info_2": 0,
	"_size_other_hdd": 0,
	"_sort_priority": 100,
	"_uninstallable": 1,
	"_view_category": 0,
	"_working_status": 0,
}

_APPINFO_HDD_ONLY = {
	"_contents_ext_type": 0,
}

_APPINFO_DISC_ONLY = {
	"_disc_copy_type": 0,
	"_uninstalled_ac_content_id_list": 0,
}

_APPINFO_EXT_ONLY = {
	"_external_hdd_app_status": 0,
}


def get_pseudo_appinfo(sfo, size, hdd_location=0, access_index=None,
		update_index=None, now=None, on_disc=0, external_hdd=None,
		meta_data_path=None, org_path=None, disc_copy_type=None):
	items = dict(_APPINFO_STATIC)
	if on_disc:
		items.update(_APPINFO_DISC_ONLY)
	else:
		items.update(_APPINFO_HDD_ONLY)
	if external_hdd is None:
		external_hdd = bool(int(hdd_location or 0))
	if external_hdd:
		items.update(_APPINFO_EXT_ONLY)
	title_id = ""

	if sfo is not None:
		for key in sorted(sfo.keys()):
			if key in _SFO_SKIP or key in ("#_size", "_hdd_location"):
				continue
			try:
				value = sfo[key]
			except Exception:
				continue
			if isinstance(value, bytes):
				value = value.decode("utf-8", "replace")
			if value is None:
				continue
			if isinstance(value, str) and not value.strip():
				continue
			if key == "CATEGORY" and value == "gp":
				value = "gd"
			items[key] = value
		title_id = items.get("TITLE_ID", "")

	items["#_size"] = int(size or 0)
	items["#_access_index"] = int(access_index or 0)
	items["#_update_index"] = int(update_index or 0)
	items["_hdd_location"] = int(hdd_location or 0)
	items["_contents_location"] = 1 if on_disc else 0
	items["_metadata_path"] = meta_data_path or "/user/appmeta/external/%s" % title_id
	items["_org_path"] = org_path or "%s/app/%s" % (
		"/mnt/disc" if on_disc else "/mnt/ext0/user", title_id)
	if on_disc:
		items["_disc_copy_type"] = 0 if disc_copy_type is None else int(disc_copy_type)
	if now:
		items["#_mtime"] = now
		items["#_promote_time"] = now
		items["#_last_access_time"] = now

	return items
