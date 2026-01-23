mod cli;
mod config;
mod error;

use error::CommandExit;

fn main() {
    if let Err(err) = cli::run() {
        if let Some(exit) = err.downcast_ref::<CommandExit>() {
            if let Some(message) = &exit.message {
                eprintln!("{message}");
            }
            std::process::exit(exit.code);
        }

        eprintln!("{err:?}");
        std::process::exit(1);
    }
}
