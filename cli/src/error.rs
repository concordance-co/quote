use std::error::Error;
use std::fmt;

#[derive(Debug)]
pub struct CommandExit {
    pub code: i32,
    pub message: Option<String>,
}

impl CommandExit {
    pub fn with_message(code: i32, message: impl Into<String>) -> Self {
        Self {
            code,
            message: Some(message.into()),
        }
    }
}

impl fmt::Display for CommandExit {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(message) = &self.message {
            write!(f, "{message}")
        } else {
            write!(f, "Command exited with code {}", self.code)
        }
    }
}

impl Error for CommandExit {}
