import sys
import requests
import logging
import webbrowser
from packaging.version import parse as parse_version
from PySide6 import QtWidgets
from . import settings, utils
from .localization_manager import translate

logger = logging.getLogger(f"{settings.LOG_PREFIX}_CORE.updater")

FORCE_UPDATE_CHECK_IN_DEV_MODE = False
CORE_VERSION_URL = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/refs/heads/main/version.txt"
)


def _get_version_info(url: str):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        content = response.text
        remote_info = {}
        for line in content.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.strip().split("=", 1)
                key = key.strip().upper()
                value = value.strip()
                if value.lower() in ["true", "false"]:
                    remote_info[key] = value.lower() == "true"
                else:
                    remote_info[key] = value
        return remote_info
    except requests.exceptions.RequestException as e:
        logger.warning(
            f"Could not check for updates (network error): {e}. Skipping check."
        )
    except Exception as e:
        logger.error(f"Failed to parse version file from {url}: {e}. Skipping check.")
    return None


def open_releases_page_and_exit(repo_url: str):
    releases_url = f"{repo_url.rstrip('/')}/releases"
    logger.info(f"Opening releases page for user: {releases_url}")
    try:
        if not webbrowser.open(releases_url):
            raise RuntimeError("webbrowser.open() returned False.")
        sys.exit(0)
    except Exception as e:
        logger.error(
            f"FATAL: Failed to open the releases page '{releases_url}': {e}",
            exc_info=True,
        )
        _ = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        msg_box.setWindowTitle(translate("dialog.update.failed.title"))
        msg_box.setText(translate("dialog.update.failed.text"))
        msg_box.setInformativeText(
            translate("dialog.update.failed.info_manual", url=releases_url, e=e)
        )
        msg_box.exec()
        sys.exit(1)


def _prompt_user_for_update(
    component_name: str, new_version: str, update_info: dict, is_critical: bool
):
    _ = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    msg_box = QtWidgets.QMessageBox()

    title_key = (
        "dialog.update.title.critical" if is_critical else "dialog.update.title.normal"
    )
    msg_box.setWindowTitle(translate(title_key))

    update_types = []
    if is_critical:
        update_types.append("Critical")
    if update_info.get("NEW_FEATURE"):
        update_types.append("New Feature")
    if update_info.get("BUGFIX"):
        update_types.append("Bugfix")

    type_text = (
        translate("dialog.update.info.types", types=", ".join(update_types))
        if update_types
        else ""
    )

    main_text = translate(
        "dialog.update.text", component_name=component_name, new_version=new_version
    )
    info_parts = [type_text, translate("dialog.update.info.recommended")]
    if is_critical:
        info_parts.append(translate("dialog.update.info.critical_warning"))

    msg_box.setText(main_text)
    msg_box.setInformativeText("\n".join(filter(None, info_parts)))
    msg_box.setIcon(QtWidgets.QMessageBox.Information)

    btn_update = msg_box.addButton(
        translate("dialog.update.button.update"), QtWidgets.QMessageBox.AcceptRole
    )
    btn_later = msg_box.addButton(
        translate("dialog.update.button.later"), QtWidgets.QMessageBox.RejectRole
    )

    btn_skip = None
    if not is_critical:
        btn_skip = msg_box.addButton(
            translate("dialog.update.button.skip"),
            QtWidgets.QMessageBox.DestructiveRole,
        )

    msg_box.exec()

    if msg_box.clickedButton() == btn_update:
        return "update"
    if msg_box.clickedButton() == btn_skip:
        return "skip"
    if msg_box.clickedButton() == btn_later:
        return "later"
    return "later"


def _handle_update_check(component_name: str, local_version: str, version_url: str):
    remote_info = _get_version_info(version_url)
    if not remote_info or "VERSION" not in remote_info:
        return

    remote_version = remote_info["VERSION"]
    if parse_version(remote_version) <= parse_version(local_version):
        logger.info(f"{component_name} is up to date (Version: {local_version}).")
        return

    logger.warning(f"New version for {component_name} found: {remote_version}")

    skipped_key_parts = ["updates", "skipped_versions", component_name.lower()]
    skipped_versions = (
        settings.current_settings.get(skipped_key_parts[0], {})
        .get(skipped_key_parts[1], {})
        .get(skipped_key_parts[2], [])
    )

    if remote_version in skipped_versions:
        logger.info(
            f"Skipping update for {component_name} version {remote_version} as per user settings."
        )
        return

    is_inherently_critical = remote_info.get("CRITICAL", False)

    state_key_parts = ["update_state", "last_critical_seen", component_name.lower()]
    last_critical_seen = (
        settings.current_settings.get(state_key_parts[0], {})
        .get(state_key_parts[1], {})
        .get(state_key_parts[2], "0.0.0")
    )

    is_inherited_critical = parse_version(local_version) < parse_version(
        last_critical_seen
    )
    is_final_critical = is_inherently_critical or is_inherited_critical

    if is_inherently_critical and parse_version(remote_version) > parse_version(
        last_critical_seen
    ):
        settings.current_settings.setdefault(state_key_parts[0], {}).setdefault(
            state_key_parts[1], {}
        )[state_key_parts[2]] = remote_version
        settings.save_settings()

    user_choice = _prompt_user_for_update(
        component_name, remote_version, remote_info, is_final_critical
    )

    if user_choice == "update":
        if "REPO_URL" not in remote_info:
            logger.error(
                "REPO_URL not found in version info. Cannot proceed with update."
            )
            return
        open_releases_page_and_exit(remote_info["REPO_URL"])
    elif user_choice == "skip":
        settings.current_settings.setdefault(skipped_key_parts[0], {}).setdefault(
            skipped_key_parts[1], {}
        )[skipped_key_parts[2]] = skipped_versions + [remote_version]
        settings.save_settings()
        logger.info(f"User skipped {component_name} version {remote_version}.")


def check_for_updates(app_name: str, app_version: str, app_version_url: str):
    if utils.IS_DEV_MODE and not FORCE_UPDATE_CHECK_IN_DEV_MODE:
        logger.info("Developer mode detected. Skipping update check.")
        return

    from PySide6.QtCore import QTimer

    def delayed_update_check():
        core_local_version = str(settings.current_settings.get("CORE_VERSION", "0.0"))
        _handle_update_check("Core", core_local_version, CORE_VERSION_URL)

        remote_app_info = _get_version_info(app_version_url)
        if remote_app_info and "MIN_CORE_VERSION" in remote_app_info:
            min_core_version = remote_app_info["MIN_CORE_VERSION"]
            if parse_version(core_local_version) < parse_version(min_core_version):
                logger.critical(
                    f"Core update required for new App version. Current: {core_local_version}, Required: {min_core_version}"
                )
                _ = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
                    sys.argv
                )
                msg_box = QtWidgets.QMessageBox()
                msg_box.setIcon(QtWidgets.QMessageBox.Critical)
                msg_box.setWindowTitle(translate("dialog.update.core_required.title"))
                msg_box.setText(
                    translate(
                        "dialog.update.core_required.text",
                        app_name=app_name,
                        min_core_version=min_core_version,
                    )
                )
                msg_box.setInformativeText(
                    translate("dialog.update.core_required.info")
                )
                msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
                msg_box.exec()
                core_remote_info = _get_version_info(CORE_VERSION_URL)
                if core_remote_info and "REPO_URL" in core_remote_info:
                    open_releases_page_and_exit(core_remote_info["REPO_URL"])
                else:
                    logger.error(
                        "Could not trigger core update because its REPO_URL is missing."
                    )
                return

        _handle_update_check(app_name, app_version, app_version_url)

    QTimer.singleShot(2000, delayed_update_check)
