//! Bridge for invoking Sybil-Aurora Python skills from Rust.
//!
//! Spawns `skill_runner.py` as a subprocess. The caller serialises the skill
//! name and input to JSON, writes it to the child's stdin, and reads the
//! result JSON from stdout.
//!
//! # Configuration
//!
//! | Env var           | Purpose                                      | Default  |
//! |-------------------|----------------------------------------------|----------|
//! | `SYBIL_SKILLS_ROOT` | Path to the `sybil-aurora-os/` directory  | required |
//! | `SYBIL_PYTHON`    | Python executable                            | `python` |
//!
//! # Example
//!
//! ```no_run
//! use codex_skills::python_bridge::PythonBridge;
//! use serde_json::json;
//!
//! let bridge = PythonBridge::from_env().expect("SYBIL_SKILLS_ROOT must be set");
//! let result = bridge.invoke("seo-engine", &json!({"topic": "real estate"})).unwrap();
//! assert_eq!(result["status"], "success");
//! ```

use serde_json::Value;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use thiserror::Error;

const ENV_SKILLS_ROOT: &str = "SYBIL_SKILLS_ROOT";
const ENV_PYTHON_EXE: &str = "SYBIL_PYTHON";
const DEFAULT_PYTHON: &str = "python";
const RUNNER_SCRIPT: &str = "core/skill_runner.py";
const SKILLS_SUBDIR: &str = "core/skills";

/// Error variants returned by the Python bridge.
#[derive(Debug, Error)]
pub enum PythonBridgeError {
    #[error("{ENV_SKILLS_ROOT} is not set")]
    NoSkillsRoot,

    #[error("skill runner not found at {0}")]
    RunnerNotFound(PathBuf),

    #[error("failed to spawn python process: {0}")]
    SpawnFailed(#[source] std::io::Error),

    #[error("failed to write to python stdin: {0}")]
    StdinWrite(#[source] std::io::Error),

    #[error("failed to collect python process output: {0}")]
    WaitFailed(#[source] std::io::Error),

    /// The process exited non-zero. Carries the exit code and stderr text.
    #[error("python process exited with code {code}: {stderr}")]
    ProcessError { code: i32, stderr: String },

    #[error("failed to parse python output as JSON: {0}")]
    OutputNotJson(#[source] serde_json::Error),

    #[error("io error while listing skills: {0}")]
    Io(#[source] std::io::Error),
}

/// Invokes Sybil-Aurora Python skills via a subprocess boundary.
///
/// Each call to [`invoke`] spawns a fresh Python process running
/// `core/skill_runner.py`, passes `{"skill": name, "input": input}` JSON on
/// stdin, and returns the parsed JSON response.
#[derive(Debug, Clone)]
pub struct PythonBridge {
    skills_root: PathBuf,
    python_exe: String,
}

impl PythonBridge {
    /// Construct from explicit paths.
    ///
    /// Prefer [`from_env`] for production use; this constructor is mainly
    /// useful in tests where env vars are not appropriate.
    pub fn new(skills_root: impl Into<PathBuf>, python_exe: impl Into<String>) -> Self {
        Self {
            skills_root: skills_root.into(),
            python_exe: python_exe.into(),
        }
    }

    /// Construct from environment variables.
    ///
    /// Reads `SYBIL_SKILLS_ROOT` (required) and `SYBIL_PYTHON` (optional,
    /// defaults to `"python"`).
    pub fn from_env() -> Result<Self, PythonBridgeError> {
        let root =
            std::env::var(ENV_SKILLS_ROOT).map_err(|_| PythonBridgeError::NoSkillsRoot)?;
        let python =
            std::env::var(ENV_PYTHON_EXE).unwrap_or_else(|_| DEFAULT_PYTHON.to_string());
        Ok(Self::new(root, python))
    }

    /// Invoke a Python skill by name with the given JSON input.
    ///
    /// Returns the parsed JSON response. The response may itself carry
    /// `{"status": "error", ...}` — that is a skill-level error, not a
    /// bridge error.
    pub fn invoke(&self, skill: &str, input: &Value) -> Result<Value, PythonBridgeError> {
        let runner = self.runner_path();
        if !runner.exists() {
            return Err(PythonBridgeError::RunnerNotFound(runner));
        }

        let payload = serde_json::json!({ "skill": skill, "input": input });
        let payload_bytes =
            serde_json::to_vec(&payload).expect("Value serialisation is infallible");

        let mut child = Command::new(&self.python_exe)
            .arg(&runner)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(PythonBridgeError::SpawnFailed)?;

        child
            .stdin
            .take()
            .expect("stdin was piped")
            .write_all(&payload_bytes)
            .map_err(PythonBridgeError::StdinWrite)?;

        let output = child
            .wait_with_output()
            .map_err(PythonBridgeError::WaitFailed)?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
            let code = output.status.code().unwrap_or(-1);
            return Err(PythonBridgeError::ProcessError { code, stderr });
        }

        serde_json::from_slice(&output.stdout).map_err(PythonBridgeError::OutputNotJson)
    }

    /// List all available Python skill names by scanning `core/skills/`.
    ///
    /// A directory is considered a skill if it contains a `main.py` file.
    /// Returns names in sorted order.
    pub fn list_skills(&self) -> Result<Vec<String>, PythonBridgeError> {
        let skills_dir = self.skills_root.join(SKILLS_SUBDIR);
        let mut names = Vec::new();

        for entry in std::fs::read_dir(&skills_dir).map_err(PythonBridgeError::Io)? {
            let entry = entry.map_err(PythonBridgeError::Io)?;
            let path = entry.path();
            if path.is_dir() && path.join("main.py").exists() {
                if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                    names.push(name.to_string());
                }
            }
        }

        names.sort_unstable();
        Ok(names)
    }

    /// Path to the Python runner script.
    pub fn runner_path(&self) -> PathBuf {
        self.skills_root.join(RUNNER_SCRIPT)
    }

    /// Path to the skills directory.
    pub fn skills_dir(&self) -> PathBuf {
        self.skills_root.join(SKILLS_SUBDIR)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Returns a bridge pointed at the real sybil-aurora-os directory.
    ///
    /// Integration tests that call this helper are skipped automatically when
    /// `SYBIL_SKILLS_ROOT` is not set in the environment. In the main repo CI
    /// the variable is set; in isolated environments it need not be.
    fn integration_bridge() -> Option<PythonBridge> {
        std::env::var(ENV_SKILLS_ROOT)
            .ok()
            .map(|root| PythonBridge::new(root, "python"))
    }

    // ── from_env ────────────────────────────────────────────────────────────

    #[test]
    fn from_env_errors_without_env_var() {
        let saved = std::env::var(ENV_SKILLS_ROOT).ok();
        std::env::remove_var(ENV_SKILLS_ROOT);
        let result = PythonBridge::from_env();
        if let Some(val) = saved {
            std::env::set_var(ENV_SKILLS_ROOT, val);
        }
        assert!(matches!(result, Err(PythonBridgeError::NoSkillsRoot)));
    }

    #[test]
    fn from_env_uses_default_python_when_env_unset() {
        std::env::remove_var(ENV_PYTHON_EXE);
        std::env::set_var(ENV_SKILLS_ROOT, "/tmp/fake");
        let b = PythonBridge::from_env().unwrap();
        std::env::remove_var(ENV_SKILLS_ROOT);
        assert_eq!(b.python_exe, DEFAULT_PYTHON);
    }

    // ── runner_path / skills_dir ─────────────────────────────────────────────

    #[test]
    fn runner_path_ends_with_skill_runner_py() {
        let b = PythonBridge::new("/some/root", "python");
        assert!(b.runner_path().ends_with("core/skill_runner.py"));
    }

    #[test]
    fn skills_dir_ends_with_core_skills() {
        let b = PythonBridge::new("/some/root", "python");
        assert!(b.skills_dir().ends_with("core/skills"));
    }

    #[test]
    fn runner_script_exists_on_disk() {
        let Some(b) = integration_bridge() else { return };
        assert!(
            b.runner_path().exists(),
            "expected skill_runner.py at {:?}",
            b.runner_path()
        );
    }

    #[test]
    fn skills_dir_exists() {
        let Some(b) = integration_bridge() else { return };
        assert!(b.skills_dir().is_dir());
    }

    // ── list_skills ──────────────────────────────────────────────────────────

    #[test]
    fn list_skills_returns_sorted_vec() {
        let Some(b) = integration_bridge() else { return };
        let names = b.list_skills().expect("list_skills failed");
        assert!(!names.is_empty(), "expected at least one skill");
        let mut sorted = names.clone();
        sorted.sort_unstable();
        assert_eq!(names, sorted, "list_skills must return sorted names");
    }

    #[test]
    fn list_skills_includes_known_skills() {
        let Some(b) = integration_bridge() else { return };
        let names = b.list_skills().unwrap();
        for expected in &["seo-engine", "ads-engine", "sales-agent", "quality-control"] {
            assert!(
                names.contains(&expected.to_string()),
                "expected skill '{}' not found in {:?}",
                expected,
                names
            );
        }
    }

    #[test]
    fn list_skills_errors_on_bad_root() {
        let b = PythonBridge::new("/nonexistent/path", "python");
        assert!(matches!(b.list_skills(), Err(PythonBridgeError::Io(_))));
    }

    // ── invoke ───────────────────────────────────────────────────────────────

    #[test]
    fn invoke_runner_not_found_error() {
        let b = PythonBridge::new("/nonexistent", "python");
        let result = b.invoke("seo-engine", &serde_json::json!({}));
        assert!(matches!(result, Err(PythonBridgeError::RunnerNotFound(_))));
    }

    #[test]
    fn invoke_seo_engine_returns_success() {
        let Some(b) = integration_bridge() else { return };
        let result = b
            .invoke(
                "seo-engine",
                &serde_json::json!({"topic": "real estate", "keywords": ["cap rate"]}),
            )
            .expect("invoke failed");
        assert_eq!(result["status"], "success");
    }

    #[test]
    fn invoke_unknown_skill_returns_error_status() {
        let Some(b) = integration_bridge() else { return };
        // The runner exits non-zero for unknown skills, so invoke returns Err.
        let result = b.invoke("totally-unknown-xyz", &serde_json::json!({}));
        assert!(
            result.is_err(),
            "expected Err for unknown skill, got {:?}",
            result
        );
    }

    #[test]
    fn invoke_ads_engine_returns_headline() {
        let Some(b) = integration_bridge() else { return };
        let result = b
            .invoke(
                "ads-engine",
                &serde_json::json!({
                    "product": "multifamily fund",
                    "platform": "meta",
                    "task": "creative_generation"
                }),
            )
            .expect("invoke failed");
        assert_eq!(result["status"], "success");
        assert!(result["data"]["headline"].is_string());
    }

    #[test]
    fn invoke_classify_returns_structured_output() {
        let Some(b) = integration_bridge() else { return };
        let result = b
            .invoke(
                "anthropic-core",
                &serde_json::json!({
                    "task": "classify",
                    "content": "strong multifamily deal with 6.8% cap rate"
                }),
            )
            .expect("invoke failed");
        // anthropic-core degrades gracefully with no API key
        assert_eq!(result["status"], "success");
    }
}
