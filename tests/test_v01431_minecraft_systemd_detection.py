from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_minecraft_detection_uses_systemd_when_process_is_not_running():
    assert "systemctl','list-unit-files','--type=service" in MAIN
    assert "systemctl','cat',unit,'--no-pager" in MAIN
    assert "WorkingDirectory=" in MAIN
    assert "ExecStart=" in MAIN


def test_minecraft_detection_follows_launcher_script_and_common_home_path():
    assert "inspect_script(script,workdir)" in MAIN
    assert "/home/*/minecraft/server.jar" in MAIN
    assert "Could not find/read the Minecraft server JAR." in MAIN
