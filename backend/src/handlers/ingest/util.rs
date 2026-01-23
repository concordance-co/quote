use chrono::{DateTime, TimeZone, Utc};
use serde::Deserialize;
use serde_json::Value;

use crate::utils::ApiError;

use super::Result;

pub fn deserialize_timestamp<'de, D>(
    deserializer: D,
) -> std::result::Result<DateTime<Utc>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = Value::deserialize(deserializer)?;
    parse_timestamp_value(value).ok_or_else(|| serde::de::Error::custom("invalid timestamp"))
}

pub fn deserialize_timestamp_opt<'de, D>(
    deserializer: D,
) -> std::result::Result<Option<DateTime<Utc>>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let option = Option::<Value>::deserialize(deserializer)?;
    match option {
        Some(value) => parse_timestamp_value(value)
            .map(Some)
            .ok_or_else(|| serde::de::Error::custom("invalid timestamp")),
        None => Ok(None),
    }
}

pub fn parse_timestamp_value(value: Value) -> Option<DateTime<Utc>> {
    match value {
        Value::String(s) => DateTime::parse_from_rfc3339(&s)
            .map(|dt| dt.with_timezone(&Utc))
            .ok(),
        Value::Number(num) => {
            if let Some(secs) = num.as_i64() {
                Utc.timestamp_opt(secs, 0).single()
            } else if let Some(float) = num.as_f64() {
                let secs = float.trunc() as i64;
                let nanos = ((float.fract()) * 1_000_000_000.0).round() as u32;
                Utc.timestamp_opt(secs, nanos).single()
            } else {
                None
            }
        }
        Value::Null => None,
        _ => None,
    }
}

pub fn to_i32(value: i64, field: &str) -> Result<i32> {
    i32::try_from(value)
        .map_err(|_| ApiError::BadRequest(format!("{} exceeds supported i32 range", field)))
}

pub fn to_i32_vec(values: Vec<i64>) -> Result<Vec<i32>> {
    values
        .into_iter()
        .map(|value| to_i32(value, "final_tokens"))
        .collect()
}
