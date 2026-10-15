# diy_ptz_switch – notes for AI agents

A PTZ router: one joystick (USB HID via evdev, or Pelco-D over RS-485) controls two IP PTZ cameras over VISCA-over-IP (UDP 52381), and an HTTP API (aiohttp, port **1423**, hardcoded) selects the target camera and handles presets. In production it runs on the livestreaming PC of the Mennonitengemeinde Basel-Holee as the user service `diy_ptz_switch.service`, inside the `python_venv` toolbox (Fedora Silverblue, **Python 3.13**), with `joystick_type: usb_joystick` and the cameras `cam1` = `192.168.71.3` and `cam2` = `192.168.71.4`.

## Layout

- `switch.py` → everything in one file: config loading (`--config`, default `~/.config/diy_ptz_switch/config.yml`), USB port role mapping, Pelco-D/evdev input → VISCA translation, a write queue per camera, speed levels 1–8, the HTTP handlers and `main()`. State lives in module globals (`CURRENT_TARGET`, `CURRENT_MODE`, `CURRENT_SPEED_LEVEL`).
- `dummy_cam.py` → fake VISCA camera for testing without hardware (see README "Easy Testing").
- `test3djoystick.py` → prints the button codes of the joystick. `ls_com_ports.py` → lists serial ports with USB locations.
- The README documents the config keys and the speed feature. Note: the camera IPs in its examples (`192.168.1.x`) are outdated; the production config lives in `livestreaming-pc-infra`.

## HTTP API (public interface)

| Route | Purpose |
| :--- | :--- |
| `GET /target/get` | `{"current_target": "cam1"}` |
| `POST /target/set` | JSON `{"target"}` or `?target=` |
| `POST /preset/goto` | `{"preset", "target"?}`. Without a target it uses the current one. |
| `POST /preset/save` | like goto; `target: "both"` saves on both cameras |
| `GET /mode/get`, `POST /mode/set?mode=` | `preview` / `program`. The router only **stores** this flag; the scripts in `livestreaming-pc-infra` read it to decide whether light and audio automation fire. |
| `GET /speed/get` | `{"speed_level", "max_speed_level"}` |

Route names, parameters and response keys are used by `livestreaming-pc-infra`'s scripts. Keep them backwards compatible, or flag the breakage explicitly.

## Conventions

- Keep it a small asyncio program. Don't block the event loop; send to the cameras through the existing queue (`enqueue_write`) and not directly.
- **New config key:** read it in `load_config()` / `get_config_int()` with a default and range check, and document it in the README.
- There are no tests. Test against two `dummy_cam.py` instances on `127.0.0.1` / `127.0.0.2` with a temporary config passed via `--config`.
- Untracked scratch files (e.g. `t.py`) are local experiments.

## Safety

- The real cameras are on the church LAN, and on Sundays the camera image is live. Don't send VISCA or API commands to `192.168.71.3/.4` or to the PC's API (`192.168.71.139:1423`), and don't restart the service there, without asking. Reading (`GET`) is fine.

## Sibling repos

On the dev machine, the related repos are checked out next to this one in `~/dox/src/` (`../<name>/`).

| Sibling | Interface with this repo |
| :--- | :--- |
| `livestreaming-pc-infra` | Deploys this repo (from the `master` branch of the GitHub URL), holds the production config `roles/sw_setup/files/diy_ptz_switch_config.yml` and the systemd unit `templates/diy_ptz_switch.service.j2`. Its scripts call the API (`*_goto.py`, `kameras_wechseln.py`, `select_other_cam.py`, `set_preview_cam_mode`, `set_program_cam_mode`, `save_preset`, `start_stream_plus_zaehler.py`). |
| `VulcanBoard` | `vulcan_speed_push` sends `POST /set_state?x=&y=&state=` to its API (`[x, y]` = VulcanBoard's `[row, col]`). The target button must have the states `speed_state_base_id + 1..8`. |
| `technik-dokumentation` | Full technical documentation (German). Read its `AGENTS.md` (section map) first, then only the relevant sections of `home.md`, never the whole file. Most relevant: `### Software-Stack grob erklärt` (preview/program concept) and `# Geräte-Inventar` (camera and joystick IDs/IPs). |

Rules:

* When changing the API, config keys or the speed push, check the callers and the config in `livestreaming-pc-infra` (e.g. `grep -rn '1423' ../livestreaming-pc-infra/roles`) and make the matching change, or explicitly say what needs to change there.
* Read siblings selectively, never whole repos.
* If a sibling is not checked out, say so instead of guessing its interface.

## Workflow

* **NEVER commit or push.** Leave all git history operations to the user.
* When a change is done, suggest a commit message following Conventional Commits,
  **unscoped** (`feat!: ...`, `feat: ...`, `fix: ...`, `chore: ...`, `doc: ...`, `refactor: ...`),
  lowercase, imperative, matching `git log`. If the change spans several repos, suggest
  one message per repo.
