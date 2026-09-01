use serde::{Deserialize, Serialize};
use tauri::Manager;
use std::{
    env,
    io::{BufRead, BufReader},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[derive(Clone, Deserialize, Serialize)]
struct BackendInfo {
    host: String,
    port: u16,
    ipc_token: String,
}

struct BackendProcess {
    info: BackendInfo,
    child: Child,
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[derive(Default)]
struct BackendState(Mutex<Option<BackendProcess>>);

fn development_python() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join(".venv")
        .join("Scripts")
        .join("python.exe")
}

fn jarvis_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .canonicalize()
        .unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join(".."))
}

fn bundled_sidecar(app: &tauri::AppHandle) -> Option<PathBuf> {
    if let Some(explicit) = env::var_os("JARVIS_SIDECAR_PATH") {
        return Some(PathBuf::from(explicit));
    }
    if cfg!(debug_assertions) {
        return None;
    }
    let names = [
        "jarvis-sidecar-x86_64-pc-windows-msvc.exe",
        "jarvis-sidecar.exe",
    ];
    if let Ok(resource) = app.path().resource_dir() {
        if let Some(found) = names
            .iter()
            .map(|name| resource.join(name))
            .find(|path| path.is_file())
        {
            return Some(found);
        }
    }
    // `cargo build --release` places the executable and sidecar side-by-side.
    // Keep this fallback so the desktop shortcut works before an installer is made.
    let executable_dir = env::current_exe().ok()?.parent()?.to_path_buf();
    names
        .iter()
        .map(|name| executable_dir.join(name))
        .find(|path| path.is_file())
}

fn spawn_backend(app: &tauri::AppHandle) -> Result<BackendProcess, String> {
    let bundled = bundled_sidecar(app);
    let executable = bundled.clone().unwrap_or_else(development_python);
    if !executable.is_file() {
        return Err(format!(
            "Backend executable was not found at {}. Set JARVIS_SIDECAR_PATH or create JARVIS/.venv.",
            executable.display()
        ));
    }
    let mut command = Command::new(&executable);
    let mut working_directory = jarvis_root();
    if bundled.is_none() {
        command.args([
            "-m", "jarvis.cli", "serve", "--parent-pid",
            &std::process::id().to_string(),
        ]);
    } else {
        command.env("JARVIS_LEXICAL_ONLY", "1");
        let local_data = app
            .path()
            .app_local_data_dir()
            .map_err(|error| format!("Could not resolve app data directory: {error}"))?;
        std::fs::create_dir_all(&local_data)
            .map_err(|error| format!("Could not create app data directory: {error}"))?;
        working_directory = local_data.clone();
        command.env("JARVIS_CONFIG_ROOT", &local_data);
        let state_root = local_data.join("state");
        command.env("JARVIS_STATE_ROOT", &state_root);
        command.args([
            "serve",
            "--parent-pid",
            &std::process::id().to_string(),
            "--config-root",
            &local_data.to_string_lossy(),
            "--state-root",
            &state_root.to_string_lossy(),
        ]);
    }
    command
        .current_dir(working_directory)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    command.creation_flags(0x08000000);
    let mut child = command.spawn().map_err(|error| format!("Could not start backend: {error}"))?;
    let stdout = child.stdout.take().ok_or("Backend stdout is unavailable")?;
    let mut first_line = String::new();
    BufReader::new(stdout)
        .read_line(&mut first_line)
        .map_err(|error| format!("Could not read backend bootstrap: {error}"))?;
    let info: BackendInfo = serde_json::from_str(first_line.trim())
        .map_err(|_| "Backend did not return a valid bootstrap contract".to_string())?;
    if info.host != "127.0.0.1" {
        let _ = child.kill();
        return Err("Backend refused non-loopback startup".into());
    }
    Ok(BackendProcess { info, child })
}

#[tauri::command]
fn ensure_backend(
    app: tauri::AppHandle,
    state: tauri::State<'_, BackendState>,
) -> Result<BackendInfo, String> {
    let mut guard = state.0.lock().map_err(|_| "Backend state is poisoned")?;
    if let Some(process) = guard.as_mut() {
        if process.child.try_wait().map_err(|error| error.to_string())?.is_none() {
            return Ok(process.info.clone());
        }
    }
    let process = spawn_backend(&app)?;
    let info = process.info.clone();
    *guard = Some(process);
    Ok(info)
}

pub fn run() {
    tauri::Builder::default()
        .manage(BackendState::default())
        .setup(|app| {
            let process = spawn_backend(&app.handle()).map_err(std::io::Error::other)?;
            let state = app.state::<BackendState>();
            let mut guard = state
                .0
                .lock()
                .map_err(|_| std::io::Error::other("Backend state is poisoned"))?;
            *guard = Some(process);
            Ok(())
        })
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![ensure_backend])
        .run(tauri::generate_context!())
        .expect("error while running JARVIS desktop");
}
