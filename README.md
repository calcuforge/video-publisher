# Video Publisher

A Claude Code skill for **auto-publishing videos to video websites** (Bilibili /
B站, Douyin / 抖音, WeChat Channels / 微信视频号, YouTube, and any other
platform). Agent + scripts: everything automatable is a Python script; what
cannot be automated (login, captcha, risk checks) is handled by documented
human-in-the-loop collaboration via VNC + headed Chromium (CDP).

## How It Works

- **Keyword-triggered**: "发布这个视频到B站", "上传视频到抖音", "publish this
  video to youtube".
- **Multi-platform**: each platform is a directory with a `platform_config.yaml`
  (material data structure + auto-mode defaults + CDP/login info).
- **Multi-project**: project = the video's key attribute (e.g. category); each
  project is a directory with a `project_config.yaml` (mode, publish defaults,
  cover generation config).
- **Dual mode**: Auto (default) runs on default config templates; Manual pauses
  for user review at key checkpoints (project init, material review, pre-submit).
- **First-publish flow** probes the publish page DOM via CDP, records the form
  structure into the platform config, and writes a reusable per-platform publish
  script. Later publishes are short: platform check → project check → material
  generation → publish.
- **Self-healing**: on failure the agent re-probes the page, fixes the script /
  structure, and retries (idempotent).
- **Dependencies**: comfyui-scheduler (cover image text-to-image), Playwright +
  VNC + headed Chromium (automation + human-collab), ffmpeg (video metadata).
- **Environment conventions aligned with
  [hermes-hitl-environment](https://github.com/calcuforge/hermes-hitl-environment)**:
  agents drive the shared Chromium over CDP (`9222`), humans watch/take over via
  VNC (`5900`) or noVNC (`6080/vnc.html`); ports resolve from env vars
  (`PLAYWRIGHT_CDP_URL`, `CHROME_REMOTE_DEBUGGING_PORT`, `VNC_PORT`,
  `NOVNC_PORT`) with config/defaults as fallback.

## Project Structure

```
video-publisher/
└── skills/video-publisher/
    ├── SKILL.md                    # Main skill definition (trigger, deps, modes, flows)
    ├── requirements.txt            # Python deps: requests, pyyaml, playwright
    ├── scripts/
    │   ├── lib/                    # Shared utilities
    │   │   ├── yamlutil.py         # YAML load/save
    │   │   ├── net.py              # Path/network helpers
    │   │   ├── env.py              # hermes-aligned env conventions (ports/CDP URL)
    │   │   └── cdp.py              # CDP + Playwright headed-browser helpers with
    │   │                           #   human-in-the-loop blocking waits (VNC hints)
    │   ├── tool/                   # Pipeline scripts
    │   │   ├── check_prereqs.py    # Environment check
    │   │   ├── launch_browser.py   # Launch shared headed Chromium (hermes-aligned)
    │   │   ├── init_workspace.py   # Ensure workspace/video_publiser_data
    │   │   ├── init_platform.py    # Platform dir + platform_config.yaml (alias-aware)
    │   │   ├── init_project.py     # Project dir + project_config.yaml
    │   │   ├── probe_page.py       # Publish-page DOM probe via CDP (human-collab)
    │   │   ├── generate_material.py# ffprobe metadata + comfyui-scheduler cover + materials.yaml
    │   │   └── publish_video.py    # Publish entry (runs the platform publish script)
    │   ├── publish_scripts/
    │   │   └── template_publish.py # Agent-filled template for per-platform scripts
    │   └── verify/                 # Config validation scripts
    ├── templates/                  # platform/project/default config templates
    │   └── example_configs/        # Filled-in config examples (video_publiser_data-bilibili-tech)
    └── references/                 # Agent workflow & protocol docs (Chinese)
```

## Dependencies & Setup

```bash
pip install -r skills/video-publisher/requirements.txt
playwright install chromium

# comfyui-scheduler (cover text-to-image), plus a running ComfyUI server
pip install -e <path-to>/comfyui-scheduler   # https://github.com/calcuforge/comfyui-scheduler.git
```

Also required on PATH: `ffmpeg`, `ffprobe`, Python >= 3.10. A headed Chromium
with `--remote-debugging-port=9222` (and VNC to watch it) is needed at publish
time — see `references/human-collab.md`.

## Usage

Install the skill by placing `skills/` in your Claude Code skills path, then
trigger with phrases like:

- "发布这个视频到B站"
- "上传 D:\videos\demo.mp4 到抖音，分类游戏"
- "publish the latest video to youtube"

## License

See [LICENSE](LICENSE).
